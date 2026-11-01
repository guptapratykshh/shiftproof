"""Encrypted offline backup / verified restore. Never replaces an existing directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
import tempfile
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC=b'SHIFTPROOF-BACKUP-1\n'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def read_key(path):
    key=Path(path).read_bytes()
    if len(key)!=32: raise ValueError('Backup key must be exactly 32 random bytes')
    return key

def backup(source,destination,key_path):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    key_path=Path(key_path).resolve()
    if not source.is_dir(): raise ValueError('Backup source must be an existing data directory')
    if key_path.is_relative_to(source): raise ValueError('Store the encryption key outside the data directory')
    key=read_key(key_path)
    if destination.exists() or destination.is_relative_to(source): raise ValueError('Use a new backup path outside the data directory')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='shiftproof-backup-') as tmp:
        staging=Path(tmp)/'data';staging.mkdir();manifest={}
        for path in sorted(source.rglob('*')):
            if path.is_symlink(): raise ValueError('Refusing symbolic links in data directory')
            # A verified restored directory may contain the previous archive manifest.
            if path==source/'backup-manifest.json': continue
            if not path.is_file() or path.name.endswith(('-wal','-shm','-journal','.tmp')): continue
            relative=path.relative_to(source);target=staging/relative;target.parent.mkdir(parents=True,exist_ok=True)
            if path.suffix in ('.sqlite3','.sqlite','.db'):
                with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db,sqlite3.connect(target) as out:
                    db.backup(out)
                    if out.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Database integrity check failed')
            else: shutil.copyfile(path,target)
            manifest[str(relative)]={'sha256':digest(target),'bytes':target.stat().st_size}
        if not manifest: raise ValueError('No persistent data files were found; refusing an empty backup')
        (staging/'backup-manifest.json').write_text(json.dumps({'format':1,'files':manifest},indent=2))
        archive=Path(tmp)/'data.tar'
        with tarfile.open(archive,'w') as tar: tar.add(staging,arcname='data')
        nonce=os.urandom(12);encryptor=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor()
        encryptor.authenticate_additional_data(MAGIC)
        fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        try:
            with os.fdopen(fd,'wb') as out,archive.open('rb') as inp:
                out.write(MAGIC+nonce)
                for chunk in iter(lambda:inp.read(1024*1024),b''): out.write(encryptor.update(chunk))
                out.write(encryptor.finalize());out.write(encryptor.tag)
        except BaseException:
            destination.unlink(missing_ok=True);raise
    return {'files':len(manifest),'archive_sha256':digest(destination),'encrypted':True}

def restore(archive,destination,key_path):
    archive,destination=Path(archive),Path(destination)
    if destination.exists(): raise ValueError('Restore to a new directory; never overwrite a live workspace')
    if archive.stat().st_size<=len(MAGIC)+12+16: raise ValueError('Incomplete encrypted archive')
    with tempfile.TemporaryDirectory(prefix='shiftproof-restore-') as tmp:
        decrypted=Path(tmp)/'data.tar'
        with archive.open('rb') as inp,decrypted.open('wb') as out:
            if inp.read(len(MAGIC))!=MAGIC: raise ValueError('Unrecognized backup format')
            nonce=inp.read(12);inp.seek(-16,2);tag=inp.read(16);remaining=inp.tell()-16-len(MAGIC)-12;inp.seek(len(MAGIC)+12)
            decryptor=Cipher(algorithms.AES(read_key(key_path)),modes.GCM(nonce,tag)).decryptor();decryptor.authenticate_additional_data(MAGIC)
            while remaining:
                chunk=inp.read(min(1024*1024,remaining))
                if not chunk: raise ValueError('Incomplete encrypted archive')
                remaining-=len(chunk);out.write(decryptor.update(chunk))
            out.write(decryptor.finalize())
        with tarfile.open(decrypted) as tar:
            if any(m.issym() or m.islnk() or m.isdev() for m in tar.getmembers()): raise ValueError('Unsafe archive entry')
            tar.extractall(Path(tmp)/'unpacked',filter='data')
        restored=Path(tmp)/'unpacked'/'data';manifest=json.loads((restored/'backup-manifest.json').read_text())
        if manifest.get('format')!=1 or not isinstance(manifest.get('files'),dict): raise ValueError('Unrecognized backup manifest')
        actual={str(path.relative_to(restored)) for path in restored.rglob('*') if path.is_file() and path!=restored/'backup-manifest.json'}
        if actual!=set(manifest['files']): raise ValueError('Backup manifest does not list every restored file')
        for name,entry in manifest['files'].items():
            path=restored/name
            if not path.resolve().is_relative_to(restored.resolve()) or digest(path)!=entry['sha256'] or path.stat().st_size!=entry['bytes']: raise ValueError('Backup manifest mismatch')
            if path.suffix in ('.sqlite3','.sqlite','.db'):
                with sqlite3.connect(path) as db:
                    if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Restored database failed integrity check')
        shutil.copytree(restored,destination)
    return {'verified_files':len(manifest['files']),'restored_to':str(destination)}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['keygen','backup','restore']);parser.add_argument('--key-file',required=True)
    parser.add_argument('--source');parser.add_argument('--destination');parser.add_argument('--services-stopped',action='store_true')
    args=parser.parse_args()
    if args.action=='keygen':
        fd=os.open(args.key_file,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(os.urandom(32))
        print(json.dumps({'status':'created','store_separately':True}))
    else:
        if not args.services_stopped: parser.error('Stop application and worker before a consistent multi-database backup or restore; then pass --services-stopped')
        if not args.source or not args.destination: parser.error('--source and --destination are required')
        print(json.dumps((backup if args.action=='backup' else restore)(args.source,args.destination,args.key_file)))
