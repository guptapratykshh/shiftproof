import {test as base, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {resolve, basename} from 'node:path';

// Each browser scenario gets a fresh auth-attempt budget in the isolated test DB.
// Otherwise 50 independent scenarios exceed the production 30-signups/5min IP cap.
// Production code and within-scenario rate limiting remain unchanged.
export const test=base.extend<{identityQuota:void}>({
 identityQuota:[async({},use)=>{
  const directory=process.env.SHIFTPROOF_BROWSER_DATA_DIR;
  if(!directory || !/^e2e-\d+$/.test(basename(directory)))throw new Error('Expected isolated e2e identity database');
  execFileSync('../.venv/bin/python',['-c',
   "import sqlite3,sys; from pathlib import Path; p=Path(sys.argv[1]); sys.exit(0) if not p.exists() else None; db=sqlite3.connect(p); db.execute('DELETE FROM limits'); db.commit(); db.close()",
   resolve(directory,'accounts','identity.sqlite3')]);
  await use();
 },{auto:true}],
});
export {expect};
export type {Page} from "@playwright/test";
