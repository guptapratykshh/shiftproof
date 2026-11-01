import { Select } from "../components/Select";
import { AppearanceControl } from "../theme";
import { tr, LanguageButton } from "../i18n";
import { lazy, Suspense, useState } from "react";
import {
  CheckCheck,
  Mic,
  ShieldCheck,
  ClipboardCheck,
  CircleAlert,
} from "lucide-react";
import type { Industry } from "./client";
import { industryExamples } from "./client";
const Scene = lazy(() => import("./Scene"));
export function Brand() {
  return (
    <a href="/" className="public-brand">
      <span>
        <CheckCheck size={23} />
      </span>
      shiftproof<span className="brand-period">.</span>
    </a>
  );
}
export default function Landing({ industries }: { industries: Industry[] }) {
  const [selected, setSelected] = useState("manufacturing");
  const item = industries.find((i) => i.id === selected);
  const example = industryExamples[selected];
  return (
    <div className="public-site">
      <nav className="public-nav">
        <Brand />
        <div className="nav-links">
          <a href="#industries">{tr("Industries")}</a>
          <a href="#how-it-works">{tr("How it works")}</a>
        </div>
        <div className="nav-actions">
          <LanguageButton /><AppearanceControl />
          <a href="/signin">{tr("Sign in")}</a>
          <a href="/signup" className="button-dark">
            {tr("Create organization")}
            
          </a>
        </div>
      </nav>
      <main>
        <section className="landing-hero">
          <div className="hero-editorial">
            <div className="eyebrow">
              <span />
              {tr("THE NEXT SHIFT STARTS WITH CLARITY")}
            </div>
            <h1>
              {tr("Work changes hands.")}
              <br />
              <em>{tr("The details shouldn’t.")}</em>
            </h1>
            <p>
              {tr(
                "Turn spoken updates into a handover people can trust. Keep unfinished work visible, resolve conflicting reports, and follow every decision back to its source.",
              )}
            </p>
            <div className="hero-actions">
              <a className="button-orange" href="/signup">
                {tr("Build your workspace")}
                
              </a>
              <a className="button-outline" href="/signin">
                {tr("Sign in")}
              </a>
            </div>
            <div className="hero-footnote">
              <span>{tr("Hindi & Hinglish voice")}</span>
              <i />
              {tr("Human-reviewed decisions")}
              <i />
              <span>{tr("Your organization’s workspace")}</span>
            </div>
          </div>
          <div className="hero-visual">
            <div className="scene-topline">
              <span>{tr("01 / THE HANDOVER IN MOTION")}</span>
              <span className="live-dot">{tr("Illustrative scenario")}</span>
            </div>
            <Select
              className="scene-industry-select"
              aria-label={tr("3D scene industry")}
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              {industries.map((i) => (
                <option value={i.id} key={i.id}>
                  {tr(i.name)}
                  {i.status === "preview" ? tr(" · planned") : ""}
                </option>
              ))}
            </Select>
            <Suspense
              fallback={
                <div className="industry-scene scene-fallback">
                  {tr("Loading the handover scene…")}
                </div>
              }
            >
              <Scene industry={selected} />
            </Suspense>
            <div className="scene-report">
              <span className="report-icon">
                <CheckCheck size={18} />
              </span>
              <div>
                <small>{tr("LATEST REPORT")}</small>
                <strong>{tr(example.update)}</strong>
              </div>
              <span className="reported-tag">{tr("Reported")}</span>
            </div>
            <div className="scene-hold">
              <CircleAlert size={18} />
              <div>
                <strong>{tr(example.issue)}</strong>
                <span>
                  {tr("A newer update doesn’t erase an unresolved condition.")}
                </span>
              </div>
            </div>
            <div className="scene-bottom">
              <span>{tr("Every update has a source.")}</span>
              <span>{tr("Every shift has a next step.")}</span>
            </div>
          </div>
        </section>
        <section id="industries" className="industry-section">
          <div className="section-intro">
            <span className="eyebrow">
              {tr("ONE PRINCIPLE. DIFFERENT WORKPLACES.")}
            </span>
            <h2>
              {tr("Built around the work")}
              <br />
              {tr("you hand over.")}
            </h2>
            <p>
              {tr(
                "Your organization type determines what you track, who reviews it, and what still needs verification.",
              )}
            </p>
          </div>
          <div
            className="industry-picker"
            role="group"
            aria-label={tr("Explore organization types")}
          >
            {industries.map((i) => (
              <button
                key={i.id}
                aria-pressed={selected === i.id}
                onClick={() => setSelected(i.id)}
                className={selected === i.id ? "selected" : ""}
              >
                <span>{tr(i.name)}</span>
                <small>
                  {i.status === "preview"
                    ? tr("Planned workflow")
                    : tr("Working workflow")}
                </small>
                
              </button>
            ))}
          </div>
          <div className="industry-explanation">
            <span className="industry-number">
              {String(
                industries.findIndex((i) => i.id === selected) + 1,
              ).padStart(2, "0")}
            </span>
            <div>
              <h3>
                {(item?.name ? tr(item.name) : "") || tr("Manufacturing")}
              </h3>
              <p>
                {tr(example.update)}
                {tr(". But:")} <strong>{tr(example.issue)}.</strong>
              </p>
              <span>
                {tr("Next action:")} {tr(example.action)}.
              </span>
            </div>
            <span className="availability">
              {item?.status === "preview"
                ? tr("Preview · operational capture not enabled")
                : tr("Available · private workspaces")}
            </span>
          </div>
        </section>
        <section id="how-it-works" className="steps-section">
          <span className="eyebrow">
            {tr("FROM A SPOKEN UPDATE TO A SHARED UNDERSTANDING")}
          </span>
          <h2>{tr("Say it. Check it. Carry it forward.")}</h2>
          <div className="steps-grid">
            {[
              [
                Mic,
                "01",
                "Report naturally",
                "Record a short update. Inspect the transcript before extracting claims.",
              ],
              [
                CircleAlert,
                "02",
                "Keep the conditions",
                "Packing complete and inspection pending remain separate reports.",
              ],
              [
                ShieldCheck,
                "03",
                "Review the evidence",
                "An authorized person reviews the source and records their decision.",
              ],
              [
                ClipboardCheck,
                "04",
                "Acknowledge the version",
                "The incoming shift acknowledges exactly what they received.",
              ],
            ].map(([Icon, n, title, desc]) => {
              const I = Icon as typeof Mic;
              return (
                <article key={String(n)}>
                  <div>
                    <I size={23} />
                    <span>{String(n)}</span>
                  </div>
                  <h3>{tr(String(title))}</h3>
                  <p>{tr(String(desc))}</p>
                </article>
              );
            })}
          </div>
        </section>
        <section className="closing-cta">
          <span className="eyebrow">
            {tr("LEAVE THE NEXT SHIFT BETTER INFORMED")}
          </span>
          <h2>
            {tr("The work continues.")}
            <br />
            {tr("So should the context.")}
          </h2>
          <a href="/signup" className="button-orange">
            {tr("Create your organization")}
            
          </a>
          <p>
            <a href="/signin">{tr("Sign in")}</a>
          </p>
        </section>
      </main>
      <footer className="public-footer">
        <Brand />
        <span>{tr("Voice handovers. Visible evidence. Human decisions.")}</span>
        <a href="/signin">
          {tr("Sign in")}
          
        </a>
      </footer>
    </div>
  );
}
