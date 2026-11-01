"""Deploy the SAM backend and Amplify frontend using existing AWS credentials.

Default is real Bedrock extraction. --scripted-demo is explicit and visible in the UI.
No Gnani key is read from command-line arguments or written to deployment outputs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import zipfile
import boto3
import httpx
from botocore.exceptions import EndpointConnectionError, ConnectionClosedError

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'.local'
STACK='shiftproof-demo'
REGION='us-east-1'

def run(args,**kwargs):
    subprocess.run(args,check=True,cwd=ROOT,**kwargs)

def wait_stack(cf, desired):
    failures=0
    while True:
        try:
            stack=cf.describe_stacks(StackName=STACK)['Stacks'][0]
            failures=0
        except (EndpointConnectionError, ConnectionClosedError):
            failures+=1
            if failures>5:
                raise RuntimeError('AWS connection interrupted. The stack may still be deploying. Inspect its status and rerun this script when connectivity returns.')
            print('AWS connection interrupted; retrying status check.',flush=True)
            time.sleep(10)
            continue
        status=stack['StackStatus']
        if status==desired:return stack
        if any(x in status for x in ('FAILED','ROLLBACK')):
            events=cf.describe_stack_events(StackName=STACK)['StackEvents']
            errors=[{'resource':e['LogicalResourceId'],'reason':e.get('ResourceStatusReason')} for e in events if 'FAILED' in e['ResourceStatus']]
            raise RuntimeError(json.dumps(errors))
        print(f'CloudFormation: {status}',flush=True);time.sleep(10)

def deploy(scripted=False,skip_bundle=False):
    if os.getenv('SHIFTPROOF_ALLOW_LEGACY_AWS_DEMO') != 'true':
        raise RuntimeError('Legacy AWS demo deployment is archived and does not support organization accounts. Use deployment/compose.yaml for the pilot. AWS remains paused.')
    LOCAL.mkdir(exist_ok=True)
    session=boto3.Session(region_name=REGION)
    account=session.client('sts').get_caller_identity()['Account']
    s3=session.client('s3');cf=session.client('cloudformation');amplify=session.client('amplify')
    bucket=f'shiftproof-artifacts-{account}-{REGION}'
    try:s3.head_bucket(Bucket=bucket)
    except Exception:
        s3.create_bucket(Bucket=bucket)
        s3.put_public_access_block(Bucket=bucket,PublicAccessBlockConfiguration={k:True for k in ('BlockPublicAcls','IgnorePublicAcls','BlockPublicPolicy','RestrictPublicBuckets')})
        s3.put_bucket_lifecycle_configuration(Bucket=bucket,LifecycleConfiguration={'Rules':[{'ID':'ExpireBuildArtifacts','Status':'Enabled','Filter':{'Prefix':'builds/'},'Expiration':{'Days':30}}]})
    bundle=LOCAL/'lambda'
    if not skip_bundle:
        if bundle.exists():shutil.rmtree(bundle)
        bundle.mkdir()
        run([sys.executable,'-m','pip','install','--platform','manylinux_2_28_x86_64','--platform','manylinux2014_x86_64','--platform','manylinux_2_34_x86_64','--implementation','cp','--python-version','3.12','--only-binary=:all:','--target',str(bundle),'-r',str(ROOT/'backend/requirements.txt')])
    target=bundle/'shiftproof'
    if target.exists():shutil.rmtree(target)
    shutil.copytree(ROOT/'backend/shiftproof',target,ignore=shutil.ignore_patterns('__pycache__'))
    archive=LOCAL/'backend.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in bundle.rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:z.write(path,path.relative_to(bundle))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()[:20]
    key=f'builds/backend-{digest}.zip';s3.upload_file(str(archive),bucket,key)
    params={'CodeBucket':bucket,'CodeKey':key,'ExtractionProvider':'scripted' if scripted else 'bedrock'}
    try:
        existing=cf.describe_stacks(StackName=STACK)['Stacks'][0]
        if existing['StackStatus'].endswith('_IN_PROGRESS'):
            desired='CREATE_COMPLETE' if existing['StackStatus']=='CREATE_IN_PROGRESS' else 'UPDATE_COMPLETE'
            existing=wait_stack(cf,desired)
        outputs={x['OutputKey']:x['OutputValue'] for x in existing.get('Outputs',[])}
        if outputs.get('FrontendUrl'):params['FrontendOrigin']=outputs['FrontendUrl']
    except cf.exceptions.ClientError as exc:
        if 'does not exist' not in str(exc):raise
        existing=None
    def apply(parameters):
        args={'StackName':STACK,'TemplateBody':(ROOT/'infra/template.yaml').read_text(),'Parameters':[{'ParameterKey':k,'ParameterValue':v} for k,v in parameters.items()],'Capabilities':['CAPABILITY_IAM','CAPABILITY_AUTO_EXPAND'],'Tags':[{'Key':'Project','Value':'ShiftProof'}]}
        if existing:
            try:cf.update_stack(**args)
            except cf.exceptions.ClientError as exc:
                if 'No updates are to be performed' in str(exc):return cf.describe_stacks(StackName=STACK)['Stacks'][0]
                raise
            return wait_stack(cf,'UPDATE_COMPLETE')
        cf.create_stack(**args)
        return wait_stack(cf,'CREATE_COMPLETE')
    stack=apply(params);outputs={x['OutputKey']:x['OutputValue'] for x in stack['Outputs']}
    if params.get('FrontendOrigin')!=outputs['FrontendUrl']:
        existing=stack;params['FrontendOrigin']=outputs['FrontendUrl'];stack=apply(params)
        outputs={x['OutputKey']:x['OutputValue'] for x in stack['Outputs']}
    (LOCAL/'deployment.json').write_text(json.dumps(outputs,indent=2)+'\n')
    print('Backend deployed; seeding fictional evidence.',flush=True)
    result=session.client('lambda').invoke(FunctionName=outputs['WorkerFunctionName'],Payload=json.dumps({'action':'seed'}).encode())
    payload=json.loads(result['Payload'].read())
    if result.get('FunctionError'):raise RuntimeError(f'Seed failed: {payload}')
    print('Seed result:',payload,flush=True)
    # Credentials are generated once and saved locally with restrictive permissions.
    cognito=session.client('cognito-idp');accounts_path=LOCAL/'demo-accounts.json'
    accounts=json.loads(accounts_path.read_text()) if accounts_path.exists() else {}
    for role in ('operator','supervisor','quality'):
        username=f'shiftproof-{role}'
        try:cognito.admin_get_user(UserPoolId=outputs['UserPoolId'],Username=username)
        except cognito.exceptions.UserNotFoundException:
            password=secrets.token_urlsafe(22)+'aA1!'
            cognito.admin_create_user(UserPoolId=outputs['UserPoolId'],Username=username,MessageAction='SUPPRESS')
            cognito.admin_set_user_password(UserPoolId=outputs['UserPoolId'],Username=username,Password=password,Permanent=True)
            accounts[role]={'username':username,'password':password}
        cognito.admin_add_user_to_group(UserPoolId=outputs['UserPoolId'],Username=username,GroupName=role)
    fd=os.open(accounts_path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(accounts,f,indent=2)
    subprocess.run(['npm','run','build'],cwd=ROOT/'frontend',env={**os.environ,'VITE_API_URL':outputs['ApiUrl']},check=True)
    webzip=LOCAL/'frontend.zip'
    with zipfile.ZipFile(webzip,'w',zipfile.ZIP_DEFLATED) as z:
        for path in (ROOT/'frontend/dist').rglob('*'):
            if path.is_file():z.write(path,path.relative_to(ROOT/'frontend/dist'))
    job=amplify.create_deployment(appId=outputs['AmplifyAppId'],branchName='main')
    with webzip.open('rb') as f:
        response=httpx.put(job['zipUploadUrl'],content=f.read(),timeout=90);response.raise_for_status()
    amplify.start_deployment(appId=outputs['AmplifyAppId'],branchName='main',jobId=job['jobId'])
    while True:
        detail=amplify.get_job(appId=outputs['AmplifyAppId'],branchName='main',jobId=job['jobId'])['job']['summary']
        print('Amplify:',detail['status'],flush=True)
        if detail['status']=='SUCCEED':break
        if detail['status'] in ('FAILED','CANCELLED'):raise RuntimeError('Amplify deployment did not succeed')
        time.sleep(10)
    print(json.dumps({'site':outputs['FrontendUrl'],'api':outputs['ApiUrl'],'mode':params['ExtractionProvider'],'credentials_file':str(accounts_path)},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scripted-demo',action='store_true');parser.add_argument('--skip-bundle',action='store_true');args=parser.parse_args();deploy(args.scripted_demo,args.skip_bundle)
