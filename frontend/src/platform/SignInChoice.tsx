import { Building2, ClipboardCheck, HardHat } from "lucide-react";
import { LanguageButton, tr } from "../i18n";
import { AppearanceControl } from "../theme";
import { Brand } from "./Landing";
import "./sign-in.css";

export const signInOptions = [
  {
    id: "worker",
    title: "Sign in as a worker",
    description: "Send spoken updates and see your assigned work.",
    loginDescription: "Use the email address your organisation invited you with.",
    href: "/worker/login",
    icon: HardHat,
  },
  {
    id: "supervisor",
    title: "Sign in as a supervisor",
    description: "Check your team's reports and prepare the next handover.",
    loginDescription: "Use your supervisor email and password to open your team's workspace.",
    href: "/login?role=supervisor",
    icon: ClipboardCheck,
  },
  {
    id: "organization",
    title: "Sign in as an organisation",
    description: "Manage your organisation, people and workplace settings.",
    loginDescription: "Use your owner or administrator email and password.",
    href: "/login?role=organization",
    icon: Building2,
  },
] as const;

export default function SignInChoice() {
  return (
    <div className="sign-in-choice">
      <header className="sign-in-header">
        <Brand />
        <div className="sign-in-controls"><LanguageButton /><AppearanceControl /></div>
      </header>
      <main>
        <div className="sign-in-intro">
          <span className="eyebrow">{tr("WELCOME BACK")}</span>
          <h1>{tr("How would you like to sign in?")}</h1>
          <p>{tr("Choose how you work with your team.")}</p>
        </div>
        <div className="sign-in-options">
          {signInOptions.map(({ id, title, description, href, icon: Icon }) => (
            <a key={id} href={href} className="sign-in-option" aria-labelledby={`sign-in-${id}`}>
              <span className="sign-in-icon"><Icon size={28} aria-hidden="true" /></span>
              <h2 id={`sign-in-${id}`}>{tr(title)}</h2>
              <p>{tr(description)}</p>
              <span className="sign-in-continue">{tr("Continue")}</span>
            </a>
          ))}
        </div>
        <p className="sign-in-new">{tr("New to ShiftProof?")} <a href="/signup">{tr("Create an organization")}</a></p>
        <a className="sign-in-back" href="/">{tr("Back to ShiftProof")}</a>
      </main>
    </div>
  );
}
