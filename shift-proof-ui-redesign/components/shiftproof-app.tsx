'use client'

import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  Check,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Clock3,
  FileAudio,
  FileText,
  Home,
  Languages,
  LayoutDashboard,
  ListChecks,
  Menu,
  Mic,
  Moon,
  MoreHorizontal,
  Play,
  Settings,
  ShieldCheck,
  Sun,
  Users,
  Volume2,
  X,
} from 'lucide-react'

type Role = 'worker' | 'manager'
type Section = 'home' | 'work' | 'handover' | 'overview' | 'reports' | 'team' | 'settings'

const workerNav = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'work', label: 'My work', icon: ListChecks },
  { id: 'handover', label: 'Handover', icon: ClipboardCheck },
] as const

const managerNav = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'work', label: 'Work items', icon: ListChecks },
  { id: 'reports', label: 'Reports & evidence', icon: FileText },
  { id: 'handover', label: 'Handover', icon: ClipboardCheck },
  { id: 'team', label: 'Team', icon: Users },
  { id: 'settings', label: 'Settings', icon: Settings },
] as const

function StatusBadge({ tone, children }: { tone: 'success' | 'warning' | 'danger' | 'info'; children: React.ReactNode }) {
  return <span className={`status status-${tone}`}><span className="status-dot" aria-hidden="true" />{children}</span>
}

function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return <header className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="page-description">{description}</p></div>{action}</header>
}

function EmptyState({ title, body, action }: { title: string; body: string; action?: string }) {
  return <div className="empty-state"><div className="empty-icon"><ListChecks size={24} /></div><h3>{title}</h3><p>{body}</p>{action && <button className="button button-secondary">{action}<ArrowRight size={16} /></button>}</div>
}

function HomeView({ onRecord, role }: { onRecord: () => void; role: Role }) {
  const isManager = role === 'manager'
  return <>
    <PageHeader eyebrow={isManager ? 'Operations control' : 'Morning shift · Assembly'} title={isManager ? 'Good morning, Divyanshi' : 'Ready when you are, user1'} description={isManager ? 'Here is what needs your attention across the floor.' : 'Capture a clear update before the next handover.'} action={<button className="icon-button" aria-label="Notifications"><Bell size={19} /><span className="notification-dot" /></button>} />
    {isManager ? <ManagerOverview /> : <WorkerHome onRecord={onRecord} />}
  </>
}

function WorkerHome({ onRecord }: { onRecord: () => void }) {
  return <div className="worker-home">
    <section className="record-hero">
      <div className="record-copy"><span className="label-chip"><Mic size={14} /> Voice-first reporting</span><h2>What happened on your shift?</h2><p>Speak naturally in Hindi, Hinglish, or English. We&apos;ll turn it into a clear update for your team.</p><button className="record-button" onClick={onRecord}><span className="record-button-icon"><Mic size={28} /></span><span><strong>Record an update</strong><small>Tap to start speaking</small></span></button></div><div className="record-art" aria-hidden="true"><div className="pulse-ring ring-one" /><div className="pulse-ring ring-two" /><div className="microphone-mark"><Mic size={48} /></div></div>
    </section>
    <div className="content-grid two-columns"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">Your shift</p><h2>Assigned work</h2></div><button className="text-button">View all <ArrowRight size={15} /></button></div><div className="task-row"><div className="task-icon"><ShieldCheck size={19} /></div><div className="task-content"><strong>Line 3 · Pump assembly</strong><span>Check seal pressure before 14:00</span></div><StatusBadge tone="warning">Needs update</StatusBadge></div><div className="task-row"><div className="task-icon task-icon-muted"><Check size={19} /></div><div className="task-content"><strong>Batch 24-018</strong><span>Material count confirmed</span></div><StatusBadge tone="success">On track</StatusBadge></div></section><section className="panel soft-panel"><div className="panel-heading"><div><p className="eyebrow">Before you leave</p><h2>Shift handover</h2></div><Clock3 size={20} className="muted-icon" /></div><p className="panel-body">One outstanding item is waiting for the incoming shift.</p><button className="button button-secondary button-full">Review handover <ArrowRight size={16} /></button></section></div>
    <section className="panel recent-panel"><div className="panel-heading"><div><p className="eyebrow">Your activity</p><h2>Recent updates</h2></div><button className="text-button">See history <ArrowRight size={15} /></button></div><div className="activity-row"><div className="activity-icon"><FileAudio size={18} /></div><div><strong>Material count · Batch 24-018</strong><span>Submitted today at 09:42 · Hindi</span></div><StatusBadge tone="info">Awaiting review</StatusBadge></div></section>
  </div>
}

function ManagerOverview() {
  return <div className="manager-home"><section className="attention-panel"><div className="attention-heading"><div><p className="eyebrow">Needs attention</p><h2>Keep the floor moving</h2></div><StatusBadge tone="warning">3 open items</StatusBadge></div><div className="attention-list"><div className="attention-row"><div className="severity severity-danger"><AlertTriangle size={18} /></div><div><strong>Seal pressure check is unresolved</strong><span>Line 3 · Reported by user1 · 18 min ago</span></div><button className="row-action">Review <ArrowRight size={15} /></button></div><div className="attention-row"><div className="severity severity-warning"><Clock3 size={18} /></div><div><strong>Handover acknowledgement pending</strong><span>Assembly · Incoming shift starts in 42 min</span></div><button className="row-action">Open <ArrowRight size={15} /></button></div><div className="attention-row"><div className="severity severity-info"><FileText size={18} /></div><div><strong>New report ready for review</strong><span>Batch 24-018 · Material count · Hindi</span></div><button className="row-action">Review <ArrowRight size={15} /></button></div></div></section><div className="stat-grid"><div className="stat-card"><span>Open holds</span><strong>02</strong><small><span className="trend-bad">↑ 1</span> since last shift</small></div><div className="stat-card"><span>Reports to review</span><strong>04</strong><small>Across 3 work items</small></div><div className="stat-card"><span>Handover status</span><strong>86%</strong><small><span className="trend-good">On track</span> for this shift</small></div></div><div className="content-grid two-columns"><section className="panel"><div className="panel-heading"><div><p className="eyebrow">Live register</p><h2>Work items</h2></div><button className="text-button">Open register <ArrowRight size={15} /></button></div><div className="table-list"><div className="table-row"><div><strong>Line 3 · Pump assembly</strong><span>Assembly · Current shift</span></div><StatusBadge tone="danger">Open hold</StatusBadge></div><div className="table-row"><div><strong>Batch 24-018</strong><span>Quality · Morning shift</span></div><StatusBadge tone="warning">Review needed</StatusBadge></div><div className="table-row"><div><strong>Packaging line 2</strong><span>Packaging · Current shift</span></div><StatusBadge tone="success">On track</StatusBadge></div></div></section><section className="panel soft-panel"><div className="panel-heading"><div><p className="eyebrow">Latest activity</p><h2>Team updates</h2></div><MoreHorizontal size={20} className="muted-icon" /></div><div className="mini-activity"><span className="avatar avatar-purple">U</span><div><strong>user1 submitted an update</strong><span>Material count · 9 min ago</span></div></div><div className="mini-activity"><span className="avatar avatar-green">R</span><div><strong>Ravi acknowledged handover</strong><span>Assembly · 24 min ago</span></div></div></section></div></div>
}

function WorkView({ role }: { role: Role }) {
  const worker = role === 'worker'
  return <><PageHeader eyebrow={worker ? 'My work' : 'Operations'} title={worker ? 'My work' : 'Work items'} description={worker ? 'Your assigned tasks and the next step for each.' : 'Create, assign, and review work across the current shift.'} action={<button className="button button-primary"><span>+</span> {worker ? 'Record update' : 'Add work item'}</button>} /><section className="panel"><div className="filter-bar"><div className="search-field"><span>⌕</span><input aria-label="Search work items" placeholder="Search work items..." /></div><button className="filter-button">All statuses <ChevronDown size={16} /></button></div>{worker ? <EmptyState title="No work assigned yet" body="Ask your supervisor to assign your work for this shift." action="Check assignment" /> : <div className="table-list large-list"><div className="table-row"><div><strong>Line 3 · Pump assembly</strong><span>Assembly · Morning shift · Assigned to user1</span></div><StatusBadge tone="danger">Open hold</StatusBadge><button className="row-action">Details <ArrowRight size={15} /></button></div><div className="table-row"><div><strong>Batch 24-018</strong><span>Quality · Morning shift · Assigned to user1</span></div><StatusBadge tone="warning">Review needed</StatusBadge><button className="row-action">Details <ArrowRight size={15} /></button></div></div>}</section></>
}

function HandoverView({ role }: { role: Role }) {
  const worker = role === 'worker'
  return <><PageHeader eyebrow="Shift continuity" title="Handover" description={worker ? 'Review what needs checking, then confirm what you received.' : 'See what is changing between shifts and what remains unresolved.'} action={<button className="button button-secondary"><Play size={16} /> Listen to handover</button>} /><section className="panel handover-intro"><div><p className="eyebrow">Current version · v0</p><h2>{worker ? 'Receive handover · say what needs checking' : 'Morning → Afternoon handover'}</h2><p>{worker ? 'Listen to the outstanding work, record what you understood, then confirm receipt.' : '2 items are carrying forward. One acknowledgement is still pending.'}</p></div><StatusBadge tone="warning">1 acknowledgement pending</StatusBadge></section><section className="panel"><div className="panel-heading"><div><p className="eyebrow">Outstanding work</p><h2>What needs checking</h2></div><span className="count-pill">2 items</span></div><div className="handover-item"><div className="severity severity-danger"><AlertTriangle size={18} /></div><div><strong>Line 3 seal pressure</strong><span>Verify pressure after maintenance before restarting the line.</span></div><StatusBadge tone="danger">Unresolved</StatusBadge></div><div className="handover-item"><div className="severity severity-warning"><Clock3 size={18} /></div><div><strong>Batch 24-018 material count</strong><span>Confirm the final quantity against the pallet label.</span></div><StatusBadge tone="warning">Verify</StatusBadge></div></section><section className="panel readback-panel"><div className="panel-heading"><div><p className="eyebrow">Step 2 of 2</p><h2>{worker ? 'Say what you understood' : 'Acknowledgement status'}</h2></div><CheckCircle2 size={23} className="success-icon" /></div>{worker ? <><p className="panel-body">Your readback is saved privately until you submit it.</p><button className="button button-primary"><Mic size={17} /> Record readback</button><button className="button button-accent"><Check size={17} /> I received this handover · confirm</button></> : <div className="ack-row"><span className="avatar avatar-purple">U</span><div><strong>user1 · Incoming shift</strong><span>Waiting for acknowledgement</span></div><button className="button button-secondary">Send reminder</button></div>}</section></>
}

function ReportsView() {
  return <><PageHeader eyebrow="Trust & evidence" title="Reports & evidence" description="Review what was reported, what was extracted, and what is verified." action={<button className="button button-secondary">Export view</button>} /><div className="content-grid report-grid"><section className="panel"><div className="filter-bar"><div className="search-field"><span>⌕</span><input aria-label="Search reports" placeholder="Search reports..." /></div><button className="filter-button">Needs review <ChevronDown size={16} /></button></div><div className="report-list"><div className="report-card active"><div className="report-title"><FileAudio size={18} /><strong>Material count · Batch 24-018</strong><StatusBadge tone="warning">Review</StatusBadge></div><p>“Pallet mein 48 pieces hain, label se check kar lena.”</p><span>user1 · Hindi · 9 min ago</span></div><div className="report-card"><div className="report-title"><FileAudio size={18} /><strong>Seal pressure · Line 3</strong><StatusBadge tone="danger">Conflict</StatusBadge></div><p>Pressure reading differs from the previous shift report.</p><span>Ravi · Hinglish · 18 min ago</span></div></div></section><aside className="panel evidence-panel"><p className="eyebrow">Selected report</p><h2>Material count · Batch 24-018</h2><div className="evidence-block"><span className="evidence-label">Reported by worker</span><p>“Pallet mein 48 pieces hain, label se check kar lena.”</p></div><div className="evidence-block ai-block"><span className="evidence-label"><span className="ai-dot" /> AI extracted</span><div className="claim-row"><strong>Quantity</strong><StatusBadge tone="warning">Needs confirmation</StatusBadge></div><p>48 pieces · Evidence: transcript only</p></div><div className="evidence-actions"><button className="button button-primary button-full">Confirm quantity</button><button className="button button-secondary button-full">Request correction</button></div></aside></div></>
}

function TeamView() {
  return <><PageHeader eyebrow="People & access" title="Team" description="Give each person the right responsibility for the floor." action={<button className="button button-primary">Add team member</button>} /><section className="panel"><div className="tabs"><button className="tab active">Members</button><button className="tab">Invitations</button><button className="tab">Access history</button></div><div className="filter-bar team-filter"><div className="search-field"><span>⌕</span><input aria-label="Search team" placeholder="Search by name or employee ID" /></div></div><div className="member-list"><div className="member-row"><span className="avatar avatar-purple">D</span><div><strong>Divyanshi Talreja</strong><span>Organization owner · Shift supervisor</span></div><StatusBadge tone="info">Owner</StatusBadge><button className="row-action">Manage <ArrowRight size={15} /></button></div><div className="member-row"><span className="avatar avatar-green">U</span><div><strong>user1</strong><span>Team member · Shift worker</span></div><StatusBadge tone="success">Active</StatusBadge><button className="row-action">Manage <ArrowRight size={15} /></button></div></div></section></>
}

function SettingsView({ dark, onTheme }: { dark: boolean; onTheme: (value: boolean) => void }) {
  return <><PageHeader eyebrow="Workspace controls" title="Settings" description="Configure your organization without losing sight of the floor." /><div className="settings-grid"><section className="panel settings-nav"><button className="settings-link active"><ShieldCheck size={17} /> Data policy <ArrowRight size={15} /></button><button className="settings-link"><Users size={17} /> Departments, locations & shifts <ArrowRight size={15} /></button><button className="settings-link"><Languages size={17} /> Language preferences <ArrowRight size={15} /></button><button className="settings-link"><Sun size={17} /> Appearance <ArrowRight size={15} /></button></section><section className="panel settings-content"><p className="eyebrow">Appearance</p><h2>Make ShiftProof yours</h2><p className="panel-body">Choose how the workspace looks for you. This setting only changes your view.</p><div className="theme-options"><button className={`theme-option ${!dark ? 'selected' : ''}`} onClick={() => onTheme(false)}><Sun size={19} /><span>Light</span>{!dark && <Check size={16} />}</button><button className={`theme-option ${dark ? 'selected' : ''}`} onClick={() => onTheme(true)}><Moon size={19} /><span>Dark</span>{dark && <Check size={16} />}</button></div><div className="policy-note"><ShieldCheck size={18} /><div><strong>Recording policy is protected</strong><span>Only organization owners can change how voice data is retained.</span></div></div></section></div></>
}

export default function ShiftProofApp() {
  const [role, setRole] = useState<Role>('worker')
  const [section, setSection] = useState<Section>('home')
  const [dark, setDark] = useState(false)
  const [recording, setRecording] = useState(false)
  useEffect(() => { const saved = window.localStorage.getItem('shiftproof-theme'); setDark(saved === 'dark') }, [])
  useEffect(() => { document.documentElement.classList.toggle('dark', dark); window.localStorage.setItem('shiftproof-theme', dark ? 'dark' : 'light') }, [dark])
  const nav = role === 'worker' ? workerNav : managerNav
  const selectRole = (nextRole: Role) => { setRole(nextRole); setSection(nextRole === 'worker' ? 'home' : 'overview') }
  return <div className="app-shell"><aside className="sidebar"><div className="brand"><span className="brand-mark"><Check size={19} /></span><span>shiftproof<span className="brand-dot">.</span></span></div><div className="workspace-switcher"><span className="workspace-label">Your workspace</span><strong>Divyanshi Talreja&apos;s workspace</strong><span className="workspace-meta">Manufacturing · Private</span></div><nav className="main-nav" aria-label="Main navigation">{nav.map(item => { const Icon = item.icon; return <button key={item.id} className={`nav-item ${section === item.id ? 'active' : ''}`} onClick={() => setSection(item.id as Section)}><Icon size={19} /><span>{item.label}</span></button> })}</nav><div className="sidebar-bottom"><div className="role-switch"><span>Viewing as</span><button onClick={() => selectRole(role === 'worker' ? 'manager' : 'worker')}><span className="avatar avatar-small">{role === 'worker' ? 'U' : 'D'}</span>{role === 'worker' ? 'Shift worker' : 'Manager'}<ChevronDown size={14} /></button></div><div className="profile"><span className="avatar">{role === 'worker' ? 'U' : 'D'}</span><div><strong>{role === 'worker' ? 'user1' : 'Divyanshi Talreja'}</strong><span>{role === 'worker' ? 'Team member' : 'Organization owner'}</span></div><button aria-label="More profile options"><MoreHorizontal size={18} /></button></div><button className="sign-out">Sign out</button></div></aside><main className="main-content"><div className="topbar"><div className="breadcrumb"><span>Divyanshi Talreja&apos;s workspace</span><ArrowRight size={15} /><strong>{role === 'worker' ? 'Worker space' : 'Management'}</strong></div><div className="topbar-actions"><button className="language-button"><Languages size={17} /> हिंदी</button><button className="theme-toggle" onClick={() => setDark(!dark)} aria-label="Toggle theme">{dark ? <Sun size={17} /> : <Moon size={17} />}</button><span className="top-avatar">{role === 'worker' ? 'U' : 'D'}</span><button className="mobile-menu" aria-label="Open menu"><Menu size={20} /></button></div></div><div className="page-container">{(section === 'home' || section === 'overview') && <HomeView role={role} onRecord={() => setRecording(true)} />}{section === 'work' && <WorkView role={role} />}{section === 'handover' && <HandoverView role={role} />}{section === 'reports' && role === 'manager' && <ReportsView />}{section === 'team' && role === 'manager' && <TeamView />}{section === 'settings' && role === 'manager' && <SettingsView dark={dark} onTheme={setDark} />}</div></main>{recording && <div className="modal-backdrop"><div className="record-modal" role="dialog" aria-modal="true" aria-labelledby="record-title"><button className="modal-close" onClick={() => setRecording(false)} aria-label="Close"><X size={19} /></button><span className="label-chip"><Mic size={14} /> Ready to record</span><h2 id="record-title">Record an update</h2><p>Speak naturally about what happened, what is pending, or what the next shift should verify.</p><div className="language-select"><Languages size={18} /><span>Hindi / Hinglish</span><ChevronDown size={16} /></div><div className="record-modal-control"><div className="modal-mic"><Mic size={36} /></div><span>Tap to start</span></div><button className="button button-primary button-full" onClick={() => setRecording(false)}>Start recording</button><small>Your transcript will be ready for review before you submit.</small></div></div>}</div>
}
