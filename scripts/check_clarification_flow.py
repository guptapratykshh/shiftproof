"""Live fictional clarification check; never reads organization notes or audio."""
import json
from pathlib import Path
from shiftproof import providers
from shiftproof.profiles import PROFILES

errors=[]
original=providers.validate_extraction

def validate(raw,text,context=None):
    try:
        return original(raw,text,context)
    except ValueError as error:
        errors.append({'error':str(error),'output':raw})
        raise

providers.validate_extraction=validate
question={'id':'Batch02:quality','text':'बैच Batch02 का quality check clear हुआ है, या अभी pending है?',
          'claim_ids':['fictional-dispatch'],'type':'quality','version':10}
context={'workflow':PROFILES['manufacturing'],'clarification':question}
result={'input_kind':'fictional_development_text','model':providers.model_name(),
        'prompt_version':providers.prompt_version('tenant_manufacturing'),'validation_errors':errors}
try:
    output,request_id=providers.extract('हाँ, क्वालिटी चेक पूरा हो गया है। बैच तैयार है।','Batch02',context=context)
    passed=any(c.property=='quality' and c.value=='cleared' for c in output.claims) and all(question['id'] in c.context_refs for c in output.claims)
    result.update(status='passed' if passed else 'failed',output=output.model_dump(mode='json'),request_id=request_id)
except providers.ProviderError as error:
    result.update(status='blocked',error_category=error.category)
path=Path('artifacts/clarification-validation-after.json')
path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':result['status'],'repair_attempts':len(errors),'report':str(path)}))
raise SystemExit(0 if result['status']=='passed' else 1)
