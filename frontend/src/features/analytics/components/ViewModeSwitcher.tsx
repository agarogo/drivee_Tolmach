import { useEffect, useState } from "react";
import type { AnswerEnvelope } from "../../../shared/types";
import {
  ANALYTICS_VIEW_ORDER,
  type AnalyticsViewMode,
  modeCaption,
  modeState,
  nextViewNotice,
  visibleModes,
} from "../lib/answerUi";

export function ViewModeSwitcher({
  answer,
  activeView,
  onChange,
}: {
  answer: AnswerEnvelope | null;
  activeView: AnalyticsViewMode;
  onChange: (viewMode: AnalyticsViewMode) => void;
}) {
  const [notice, setNotice] = useState("");

  useEffect(() => {
    setNotice("");
  }, [activeView, answer?.answer_type_key]);

  if (!answer || !visibleModes(answer).length) return null;

  return (
    <section className="answer-card view-mode-switcher">
      <div className="answer-card-head">
        <div>
          <span className="eyebrow">View Modes</span>
          <h4>Switch only when the backend says the current grain is compatible</h4>
        </div>
      </div>
      <div className="view-mode-grid">
        {ANALYTICS_VIEW_ORDER.map((mode) => {
          const state = modeState(answer, mode, activeView);
          return (
            <button
              key={mode}
              type="button"
              className={`view-mode-pill ${state}`}
              onClick={() => {
                if (state === "active") return;
                if (state === "ready") {
                  setNotice("");
                  onChange(mode);
                  return;
                }
                setNotice(nextViewNotice(answer, mode));
              }}
            >
              <strong>{mode}</strong>
              <span>{modeCaption(state)}</span>
            </button>
          );
        })}
      </div>
      {notice && <p className="view-mode-note">{notice}</p>}
    </section>
  );
}
