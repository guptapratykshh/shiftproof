"""Store a Gnani key without placing it in shell history or chat."""
import getpass,json
from pathlib import Path
import boto3

root=Path(__file__).resolve().parents[1]
deployment=json.loads((root/'.local/deployment.json').read_text())
key=getpass.getpass('Gnani API key (hidden): ').strip()
if not key:raise SystemExit('No key supplied; nothing changed.')
boto3.client('secretsmanager',region_name='us-east-1').put_secret_value(SecretId=deployment['GnaniSecretArn'],SecretString=json.dumps({'GNANI_API_KEY':key}))
print('Gnani key stored in AWS Secrets Manager. No credentials were printed.')
