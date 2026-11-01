"""Local SQLite and cloud DynamoDB share optimistic transaction semantics."""
from pathlib import Path
import copy
import json
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
import os
from .config import settings

COLLECTIONS = ('notes', 'claims', 'resolutions', 'acknowledgements', 'usage', 'jobs', 'snapshots')

class Conflict(Exception):
    pass

def empty_state():
    return {'version': 0, **{key: {} for key in COLLECTIONS}}

class LocalRepository:
    """Indexed, per-record local storage with the legacy state interface.

    The original ``workspace`` row is an immutable migration archive. Existing
    callers can still reconcile a complete state in a transaction, but only
    changed records are written. New read paths should use ``query_records``.
    """
    def __init__(self, path):
        self.path = str(path)
        self.data_dir = Path(path).parent
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            migrated = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspace_metadata'").fetchone()
            version = db.execute("SELECT document FROM workspace_metadata WHERE key='schema_version'").fetchone() if migrated else None
            if version and int(version[0]) >= 2:
                return
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY, document TEXT NOT NULL)')
            db.execute('INSERT OR IGNORE INTO workspace VALUES (1, ?)', (json.dumps(empty_state()),))
            db.execute('CREATE TABLE IF NOT EXISTS workspace_metadata (key TEXT PRIMARY KEY, document TEXT NOT NULL)')
            db.execute('''CREATE TABLE IF NOT EXISTS workspace_records (
                collection TEXT NOT NULL, id TEXT NOT NULL, document TEXT NOT NULL,
                batch_id TEXT, note_id TEXT, shift_id TEXT, status TEXT,
                actor_id TEXT, created_at TEXT, claim_id TEXT,
                PRIMARY KEY (collection, id))''')
            if 'claim_id' not in {row[1] for row in db.execute('PRAGMA table_info(workspace_records)')}:
                db.execute('ALTER TABLE workspace_records ADD COLUMN claim_id TEXT')
                db.execute("UPDATE workspace_records SET claim_id=json_extract(document, '$.claim_id') WHERE collection='resolutions'")
            for name, columns in {
                'item': 'collection, batch_id, id', 'note': 'collection, note_id, id',
                'shift': 'collection, shift_id, id', 'status': 'collection, status, id',
                'actor': 'collection, actor_id, id', 'time': 'collection, created_at, id', 'claim': 'collection, claim_id, id',
            }.items():
                db.execute(f'CREATE INDEX IF NOT EXISTS workspace_records_{name} ON workspace_records ({columns})')
            if not db.execute("SELECT 1 FROM workspace_metadata WHERE key='schema_version'").fetchone():
                legacy = json.loads(db.execute('SELECT document FROM workspace WHERE id=1').fetchone()[0])
                self._save(db, {}, legacy)
            db.execute("INSERT INTO workspace_metadata VALUES ('schema_version', '2') ON CONFLICT(key) DO UPDATE SET document='2'")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=5000')
        db.execute('PRAGMA synchronous=FULL')
        current_mode = db.execute('PRAGMA journal_mode').fetchone()[0].lower()
        if current_mode == 'wal' or os.getenv('SHIFTPROOF_SQLITE_WAL', 'false').lower() == 'true':
            version = sqlite3.sqlite_version_info
            patched = version >= (3, 51, 3) or ((3, 50, 7) <= version < (3, 51, 0)) or ((3, 44, 6) <= version < (3, 45, 0))
            if not patched:
                db.close()
                raise RuntimeError('WAL deployment requires SQLite 3.51.3+ or a patched 3.50.7/3.44.6 release')
            if current_mode != 'wal':
                db.execute('PRAGMA journal_mode=WAL')
        return db

    @staticmethod
    def _collections(state):
        return {key for key, value in state.items()
                if isinstance(value, dict) and (key in COLLECTIONS or all(isinstance(v, dict) for v in value.values()))}

    @staticmethod
    def _load(db):
        metadata = {key: json.loads(document) for key, document in db.execute(
            "SELECT key, document FROM workspace_metadata WHERE key != 'schema_version'")}
        names = metadata.pop('_collections', list(COLLECTIONS))
        state = {**metadata, **{name: {} for name in names}}
        for collection, ident, document in db.execute('SELECT collection, id, document FROM workspace_records ORDER BY rowid'):
            state.setdefault(collection, {})[ident] = json.loads(document)
        return state

    @classmethod
    def _save(cls, db, before, after):
        old_collections, new_collections = cls._collections(before), cls._collections(after)
        old_meta = {key: value for key, value in before.items() if key not in old_collections}
        new_meta = {key: value for key, value in after.items() if key not in new_collections}
        old_meta['_collections'], new_meta['_collections'] = sorted(old_collections), sorted(new_collections)
        for key, value in new_meta.items():
            if key not in old_meta or old_meta[key] != value:
                db.execute('INSERT INTO workspace_metadata VALUES (?,?) ON CONFLICT(key) DO UPDATE SET document=excluded.document', (key, json.dumps(value)))
        for key in old_meta.keys() - new_meta.keys():
            db.execute('DELETE FROM workspace_metadata WHERE key=?', (key,))
        for collection in old_collections | new_collections:
            previous = before.get(collection, {}) if collection in old_collections else {}
            current = after.get(collection, {}) if collection in new_collections else {}
            for ident, record in current.items():
                if ident in previous and previous[ident] == record:
                    continue
                db.execute('''INSERT INTO workspace_records (collection,id,document,batch_id,note_id,shift_id,status,actor_id,created_at,claim_id) VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(collection,id) DO UPDATE SET document=excluded.document,
                    batch_id=excluded.batch_id,note_id=excluded.note_id,shift_id=excluded.shift_id,
                    status=excluded.status,actor_id=excluded.actor_id,created_at=excluded.created_at,claim_id=excluded.claim_id''',
                    (collection, ident, json.dumps(record), record.get('batch_id') or record.get('work_item_id'), record.get('note_id'),
                     record.get('shift_id'), record.get('status'),
                     (record.get('actor') or {}).get('id') or record.get('actor_id'),
                     record.get('created_at') or record.get('received_at') or record.get('queued_at'), record.get('claim_id')))
            for ident in previous.keys() - current.keys():
                db.execute('DELETE FROM workspace_records WHERE collection=? AND id=?', (collection, ident))

    def load(self):
        with self.connect() as db:
            db.execute('BEGIN')
            return self._load(db)

    @staticmethod
    def _load_index(db):
        growing = ('notes', 'claims', 'resolutions', 'acknowledgements', 'usage', 'jobs', 'snapshots',
                   'ack_audio', 'operational_events', 'assignment_history')
        metadata = {key: json.loads(document) for key, document in db.execute(
            "SELECT key, document FROM workspace_metadata WHERE key != 'schema_version'")}
        names = metadata.pop('_collections', list(COLLECTIONS))
        state = {**metadata, **{name: {} for name in names}}
        placeholders = ','.join('?' for _ in growing)
        for collection, ident, document in db.execute(
                f'SELECT collection,id,document FROM workspace_records WHERE collection NOT IN ({placeholders}) ORDER BY rowid', growing):
            state.setdefault(collection, {})[ident] = json.loads(document)
        return state

    def load_index(self):
        """Load authorization/configuration indexes without reports or history."""
        with self.connect() as db:
            db.execute('BEGIN')
            return self._load_index(db)

    def load_scoped(self, item_ids, *, shift_ids=None):
        """Evidence-complete work-item read, with historical decisions joined by ID.

        Cross-item notes and historical snapshots are never loaded accidentally.
        Pass authorized shift IDs to include their receipts and snapshots.
        """
        item_ids = list(dict.fromkeys(item_ids))
        shifts = list(dict.fromkeys(shift_ids or []))
        with self.connect() as db:
            db.execute('BEGIN')
            state = self._load_index(db)
            state['work_items'] = {key: value for key, value in state.get('work_items', {}).items() if key in item_ids}
            self._load_scope_records(db, state, item_ids, shifts)
            # Keep the configuration index complete for authorization and the
            # organization switcher. Route serializers select visible handovers;
            # evidence, receipts, and snapshots above remain explicitly scoped.
            return state

    @staticmethod
    def _load_scope_records(db, state, item_ids, shifts=()):
        if item_ids:
            placeholders = ','.join('?' for _ in item_ids)
            query = f'''SELECT collection,id,document FROM workspace_records
                WHERE (collection IN ('notes','claims') AND batch_id IN ({placeholders}))
                OR (collection='resolutions' AND (
                    note_id IN (SELECT id FROM workspace_records WHERE collection='notes' AND batch_id IN ({placeholders}))
                    OR claim_id IN (SELECT id FROM workspace_records WHERE collection='claims' AND batch_id IN ({placeholders}))))
                OR (collection='jobs' AND note_id IN (SELECT id FROM workspace_records WHERE collection='notes' AND batch_id IN ({placeholders})))
                ORDER BY rowid'''
            for collection, ident, document in db.execute(query, item_ids * 4):
                state[collection][ident] = json.loads(document)
        if shifts:
            scope_placeholders = ','.join('?' for _ in shifts)
            for collection, ident, document in db.execute(
                    f"SELECT collection,id,document FROM workspace_records WHERE collection IN ('snapshots','acknowledgements','ack_audio','operational_events','assignment_history') AND shift_id IN ({scope_placeholders}) ORDER BY rowid", shifts):
                state[collection][ident] = json.loads(document)

    def get_record(self, collection, ident):
        with self.connect() as db:
            row = db.execute('SELECT document FROM workspace_records WHERE collection=? AND id=?', (collection, ident)).fetchone()
        return json.loads(row[0]) if row else None

    def next_due_job(self, timestamp):
        with self.connect() as db:
            row = db.execute("""SELECT document FROM workspace_records
                WHERE collection='jobs' AND json_extract(document,'$.kind')='durable'
                AND (status='queued' OR (status='running' AND COALESCE(json_extract(document,'$.lease_until'),'')<=?))
                ORDER BY created_at,id LIMIT 1""", (timestamp,)).fetchone()
        return json.loads(row[0]) if row else None

    def query_records(self, collection, *, batch_id=None, note_id=None, shift_id=None,
                      status=None, actor_id=None, limit=50, offset=0):
        """Bounded read using indexed dimensions; no workspace deserialization."""
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError('Use a limit between 1 and 200 and a nonnegative offset')
        where, args = ['collection=?'], [collection]
        for key, value in {'batch_id': batch_id, 'note_id': note_id, 'shift_id': shift_id,
                           'status': status, 'actor_id': actor_id}.items():
            if value is not None:
                where.append(key + '=?'); args.append(value)
        with self.connect() as db:
            records = db.execute('SELECT document FROM workspace_records WHERE ' + ' AND '.join(where)
                                 + ' ORDER BY created_at DESC, id LIMIT ? OFFSET ?', [*args, limit, offset]).fetchall()
        return [json.loads(row[0]) for row in records]

    @contextmanager
    def transaction(self, batch_ids=None, record_ids=None):
        scope = None if batch_ids is None else list(dict.fromkeys(batch_ids))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if scope is None:
                before = self._load(db)
            else:
                before = self._load_index(db)
                # Older pilot workspaces may have shifts but no fingerprint
                # cache. Initialize once from complete history, never from a
                # partial item read that could hide earlier evidence.
                initialize_material = bool(before.get('shift_occurrences')) and not set(before.get('work_items', {})) <= set(before.get('material_items', {}))
                if initialize_material:
                    before = self._load(db)
                else:
                    self._load_scope_records(db, before, scope)
                for ident, document in db.execute("SELECT id,document FROM workspace_records WHERE collection='usage'"):
                    before['usage'][ident] = json.loads(document)
                for collection, ids in (record_ids or {}).items():
                    for ident in ids:
                        row = db.execute('SELECT document FROM workspace_records WHERE collection=? AND id=?', (collection, ident)).fetchone()
                        if row:
                            before.setdefault(collection, {})[ident] = json.loads(row[0])
            state = copy.deepcopy(before)
            if scope is not None and not initialize_material:
                state['_transaction_batch_ids'] = scope.copy()
            yield state
            if scope is not None:
                if not initialize_material and state.get('_transaction_batch_ids') != scope:
                    raise Conflict('The internal transaction scope cannot be changed')
                self._check_scope_writes(db, before, state, set(scope))
            if (scope is None or initialize_material) and '_transaction_batch_ids' in state:
                raise Conflict('The internal transaction scope cannot be supplied by a caller')
            if state.get('shift_occurrences'):
                from .pilot_scope import sync_handovers
                sync_handovers(state, before)
            state.pop('_transaction_batch_ids', None)
            if state != before:
                self._save(db, before, state)

    @staticmethod
    def _check_scope_writes(db, before, state, item_ids):
        """Fail closed if a partial write reaches an unloaded work item's source.

        Exact-ID reads may intentionally include an unrelated record for
        idempotency checks, but never authorize changing that record.
        """
        for collection in ('notes', 'claims'):
            old, new = before.get(collection, {}), state.get(collection, {})
            for ident in old.keys() | new.keys():
                previous, current = old.get(ident), new.get(ident)
                if previous == current:
                    continue
                if any(record and record.get('batch_id') not in item_ids for record in (previous, current)):
                    raise Conflict('A scoped transaction cannot change another work item')
                if previous is None:
                    stored = db.execute('SELECT batch_id FROM workspace_records WHERE collection=? AND id=?', (collection, ident)).fetchone()
                    if stored and stored[0] not in item_ids:
                        raise Conflict('This record identifier already belongs to another work item')

class DynamoRepository:
    def __init__(self):
        import boto3
        self.table = boto3.resource('dynamodb', region_name=settings().region).Table(settings().table)
        self.client = boto3.client('dynamodb', region_name=settings().region)

    def load(self):
        # Read the version before and after the paginated query for a consistent snapshot.
        for _ in range(5):
            before = self.table.get_item(Key={'pk': 'WORKSPACE', 'sk': 'META'}, ConsistentRead=True).get('Item', {}).get('revision', 0)
            args = {'KeyConditionExpression': 'pk = :pk', 'ExpressionAttributeValues': {':pk': 'WORKSPACE'}, 'ConsistentRead': True}
            items = []
            while True:
                response = self.table.query(**args)
                items.extend(response['Items'])
                if 'LastEvaluatedKey' not in response:
                    break
                args['ExclusiveStartKey'] = response['LastEvaluatedKey']
            after = self.table.get_item(Key={'pk': 'WORKSPACE', 'sk': 'META'}, ConsistentRead=True).get('Item', {}).get('revision', 0)
            if before == after:
                state = empty_state()
                state['_revision'] = int(after)
                for item in items:
                    if item['sk'] == 'META':
                        state['version'] = int(item['version'])
                    else:
                        collection, ident = item['sk'].split('#', 1)
                        state[collection][ident] = json.loads(item['document'])
                return state
        raise Conflict('Workspace changed while reading. Please retry.')

    @contextmanager
    def transaction(self):
        from boto3.dynamodb.types import TypeSerializer
        from botocore.exceptions import ClientError
        before = self.load()
        state = copy.deepcopy(before)
        yield state
        if before == state:
            return
        ser = TypeSerializer()
        encode = lambda item: {k: ser.serialize(v) for k, v in item.items()}
        revision = before.get('_revision', 0)
        items = [{'Put': {'TableName': settings().table, 'Item': encode({'pk': 'WORKSPACE', 'sk': 'META', 'revision': revision+1, 'version': state['version']}), 'ConditionExpression': 'attribute_not_exists(revision) OR revision = :revision', 'ExpressionAttributeValues': {':revision': {'N': str(revision)}}}}]
        for collection in COLLECTIONS:
            for ident, value in state[collection].items():
                if value != before[collection].get(ident):
                    items.append({'Put': {'TableName': settings().table, 'Item': encode({'pk': 'WORKSPACE', 'sk': f'{collection}#{ident}', 'document': json.dumps(value)})}})
            for ident in before[collection].keys() - state[collection].keys():
                items.append({'Delete': {'TableName': settings().table, 'Key': encode({'pk': 'WORKSPACE', 'sk': f'{collection}#{ident}'})}})
        if len(items) > 100:
            raise ValueError('A transaction cannot change more than 99 records')
        try:
            self.client.transact_write_items(TransactItems=items)
        except ClientError as exc:
            if exc.response['Error']['Code'] == 'TransactionCanceledException':
                raise Conflict('Another update was saved. Refresh and retry.') from exc
            raise

def repository():
    config = settings()
    if config.cloud:
        return DynamoRepository()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return LocalRepository(config.data_dir / 'demo' / 'workspace.sqlite3')
