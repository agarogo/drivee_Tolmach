export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "logo compact-logo" : "logo"}>
      <span className="logo-mark" aria-hidden="true">
        <svg viewBox="0 0 16 16" fill="none">
          <path d="M3 8h10M8 3l5 5-5 5" stroke="#0a1a0c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      {!compact && (
        <>
          <span className="logo-name">Толмач</span>
          <span className="logo-sub">by Drivee</span>
        </>
      )}
    </div>
  );
}
