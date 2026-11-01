import importlib.util
import io
import json
import os
import sqlite3
import tarfile
from pathlib import Path
import pytest

def load_script():
    path=Path(__file__).resolve().parents[2]/'scripts'/'pilot_backup.py'
    spec=importlib.util.spec_from_file_location('pilot_backup',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_encrypted_backup_restore_preserves_database_audio_and_rejects_tampering(tmp_path):
    tools=load_script();source=tmp_path/'data';source.mkdir();key=tmp_path/'secret';key.write_bytes(os.urandom(32))
    with sqlite3.connect(source/'identity.sqlite3') as db:
        db.execute('CREATE TABLE evidence(id TEXT PRIMARY KEY,document TEXT)');db.execute('INSERT INTO evidence VALUES (?,?)',('original','unchanged snapshot'))
    (source/'recording.wav').write_bytes(b'original audio evidence')
    archive=tmp_path/'backup.enc';result=tools.backup(source,archive,key)
    assert result['encrypted'] and b'unchanged snapshot' not in archive.read_bytes()
    restored=tmp_path/'restored';assert tools.restore(archive,restored,key)['verified_files']==2
    assert (restored/'recording.wav').read_bytes()==(source/'recording.wav').read_bytes()
    with sqlite3.connect(restored/'identity.sqlite3') as db: assert db.execute('SELECT * FROM evidence').fetchall()==[('original','unchanged snapshot')]
    with pytest.raises(ValueError):tools.restore(archive,restored,key)
    corrupt=bytearray(archive.read_bytes());corrupt[-25]^=1;archive.write_bytes(corrupt)
    with pytest.raises(Exception):tools.restore(archive,tmp_path/'corrupted',key)
    assert not (tmp_path/'corrupted').exists()


def test_backup_rejects_missing_empty_sources_and_keys_inside_source(tmp_path):
    tools=load_script(); key=tmp_path/'secret'; key.write_bytes(os.urandom(32))
    destination=tmp_path/'backup.enc'
    with pytest.raises(ValueError,match='existing data directory'):
        tools.backup(tmp_path/'does-not-exist',destination,key)
    source=tmp_path/'data'; source.mkdir()
    with pytest.raises(ValueError,match='empty backup'):
        tools.backup(source,destination,key)
    internal=source/'secret'; internal.write_bytes(os.urandom(32))
    with pytest.raises(ValueError,match='outside the data directory'):
        tools.backup(source,destination,internal)
    alias=tmp_path/'key-link'; alias.symlink_to(internal)
    with pytest.raises(ValueError,match='outside the data directory'):
        tools.backup(source,destination,alias)
    assert not destination.exists()


def test_wrong_key_and_short_archive_never_create_restore_destination(tmp_path):
    tools=load_script();source=tmp_path/'data';source.mkdir()
    (source/'report.txt').write_text('Private source evidence')
    key=tmp_path/'key';key.write_bytes(os.urandom(32));wrong=tmp_path/'wrong';wrong.write_bytes(os.urandom(32))
    archive=tmp_path/'backup.enc';tools.backup(source,archive,key)
    with pytest.raises(Exception): tools.restore(archive,tmp_path/'wrong-restore',wrong)
    assert not (tmp_path/'wrong-restore').exists()
    archive.write_bytes(tools.MAGIC+b'partial')
    with pytest.raises(ValueError,match='Incomplete encrypted archive'):tools.restore(archive,tmp_path/'short-restore',key)
    assert not (tmp_path/'short-restore').exists()


def test_backup_handles_uri_characters_and_can_back_up_a_restored_directory(tmp_path):
    tools=load_script();source=tmp_path/'data ?#';source.mkdir();key=tmp_path/'key';key.write_bytes(os.urandom(32))
    with sqlite3.connect(source/'evidence ?#.sqlite3') as db:
        db.execute('CREATE TABLE evidence(value TEXT)');db.execute("INSERT INTO evidence VALUES ('preserved')")
    first=tmp_path/'first.enc';tools.backup(source,first,key)
    restored=tmp_path/'restored';tools.restore(first,restored,key)
    second=tmp_path/'second.enc';assert tools.backup(restored,second,key)['files']==1
    final=tmp_path/'final';assert tools.restore(second,final,key)['verified_files']==1
    with sqlite3.connect(final/'evidence ?#.sqlite3') as db:
        assert db.execute('SELECT value FROM evidence').fetchone()[0]=='preserved'


@pytest.mark.parametrize('unsafe_name',['../outside.txt','data/link','data/unlisted.txt'])
def test_even_authenticated_unsafe_archive_cannot_restore_unlisted_or_outside_files(tmp_path,unsafe_name):
    tools=load_script(); key=tmp_path/'key';key.write_bytes(os.urandom(32))
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w') as tar:
        manifest=json.dumps({'format':1,'files':{}}).encode()
        item=tarfile.TarInfo('data/backup-manifest.json');item.size=len(manifest);tar.addfile(item,io.BytesIO(manifest))
        item=tarfile.TarInfo(unsafe_name)
        if unsafe_name.endswith('/link'):
            item.type=tarfile.SYMTYPE;item.linkname=str(tmp_path/'outside.txt');tar.addfile(item)
        else:
            item.size=4;tar.addfile(item,io.BytesIO(b'evil'))
    nonce=os.urandom(12)
    encryptor=tools.Cipher(tools.algorithms.AES(key.read_bytes()),tools.modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(tools.MAGIC)
    ciphertext=encryptor.update(buffer.getvalue())+encryptor.finalize()
    archive=tmp_path/'unsafe.enc';archive.write_bytes(tools.MAGIC+nonce+ciphertext+encryptor.tag)
    with pytest.raises((ValueError,tarfile.TarError)):
        tools.restore(archive,tmp_path/'restored',key)
    assert not (tmp_path/'restored').exists()
    assert not (tmp_path/'outside.txt').exists()
