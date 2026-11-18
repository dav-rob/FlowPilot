import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Info, ShieldCheck, User, X } from "lucide-react";
import "./UserProfile.css";

type DetailKind = "profile" | "permissions";

function isOutsideDialog(
  e: React.PointerEvent<HTMLDialogElement>,
  dialog: HTMLDialogElement,
) {
  const rect = dialog.getBoundingClientRect();
  return (
    e.clientX < rect.left ||
    e.clientX > rect.right ||
    e.clientY < rect.top ||
    e.clientY > rect.bottom
  );
}

export default function UserProfile() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeDetail, setActiveDetail] = useState<DetailKind | null>(null);

  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuListRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const pendingFocusRef = useRef<"first" | "last" | null>(null);
  const pressedBackdropRef = useRef(false);

  const triggerId = useId();
  const menuId = useId();
  const dialogTitleId = useId();

  function getMenuItems(): HTMLButtonElement[] {
    if (!menuListRef.current) return [];
    return Array.from(
      menuListRef.current.querySelectorAll<HTMLButtonElement>(
        '[role="menuitem"]:not(:disabled)',
      ),
    );
  }

  useEffect(() => {
    if (!menuOpen) {
      pendingFocusRef.current = null;
      return;
    }
    const target = pendingFocusRef.current;
    pendingFocusRef.current = null;
    if (!target) return;
    const items = getMenuItems();
    if (items.length === 0) return;
    const item = target === "last" ? items[items.length - 1] : items[0];
    item?.focus();
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;

    function handleOutsidePointer(e: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }

    function handleFocusIn(e: FocusEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }

    function handleDocumentKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      const focusInside =
        rootRef.current &&
        document.activeElement &&
        rootRef.current.contains(document.activeElement);
      e.preventDefault();
      setMenuOpen(false);
      if (focusInside) {
        triggerRef.current?.focus();
      }
    }

    document.addEventListener("pointerdown", handleOutsidePointer);
    document.addEventListener("focusin", handleFocusIn);
    document.addEventListener("keydown", handleDocumentKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handleOutsidePointer);
      document.removeEventListener("focusin", handleFocusIn);
      document.removeEventListener("keydown", handleDocumentKeyDown);
    };
  }, [menuOpen]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!activeDetail || !dialog) return;
    if (!dialog.open) {
      dialog.showModal();
    }
    closeBtnRef.current?.focus();
  }, [activeDetail]);

  function openMenuWithFocus(target: "first" | "last") {
    pendingFocusRef.current = target;
    setMenuOpen(true);
  }

  function handleTriggerClick(e: React.MouseEvent<HTMLButtonElement>) {
    if (menuOpen) {
      setMenuOpen(false);
      return;
    }
    // Keyboard activation (detail === 0) enters the menu on the first item.
    if (e.detail === 0) {
      openMenuWithFocus("first");
    } else {
      setMenuOpen(true);
    }
  }

  function handleTriggerKeyDown(e: React.KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (menuOpen) {
        getMenuItems()[0]?.focus();
      } else {
        openMenuWithFocus("first");
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (menuOpen) {
        const items = getMenuItems();
        items[items.length - 1]?.focus();
      } else {
        openMenuWithFocus("last");
      }
    } else if (e.key === "Escape" && menuOpen) {
      e.preventDefault();
      e.stopPropagation();
      setMenuOpen(false);
      triggerRef.current?.focus();
    }
  }

  function handleMenuKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const items = getMenuItems();
    if (items.length === 0) return;
    const currentIndex = items.indexOf(
      document.activeElement as HTMLButtonElement,
    );

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex =
        currentIndex < 0 ? 0 : (currentIndex + 1) % items.length;
      items[nextIndex]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prevIndex =
        currentIndex < 0
          ? items.length - 1
          : (currentIndex - 1 + items.length) % items.length;
      items[prevIndex]?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      items[0]?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      items[items.length - 1]?.focus();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      setMenuOpen(false);
      triggerRef.current?.focus();
    } else if (e.key === "Tab") {
      // Return focus to the trigger synchronously before closing so Tab/Shift+Tab continues in page order.
      triggerRef.current?.focus();
      setMenuOpen(false);
    }
  }

  function openDetail(kind: DetailKind) {
    setMenuOpen(false);
    setActiveDetail(kind);
  }

  function closeDetail() {
    const dialog = dialogRef.current;
    if (dialog?.open) {
      dialog.close();
    } else {
      setActiveDetail(null);
      triggerRef.current?.focus();
    }
  }

  function handleDialogClose() {
    setActiveDetail(null);
    triggerRef.current?.focus();
  }

  return (
    <div className="up-root" ref={rootRef}>
      <button
        ref={triggerRef}
        id={triggerId}
        type="button"
        className="up-trigger"
        aria-label="Alex Morgan, Operations reviewer"
        aria-haspopup="menu"
        aria-expanded={menuOpen}
        aria-controls={menuId}
        onClick={handleTriggerClick}
        onKeyDown={handleTriggerKeyDown}
      >
        <span className="up-avatar" aria-hidden="true">
          AM
        </span>
        <span className="up-trigger-text">
          <span className="up-trigger-name">Alex Morgan</span>
          <span className="up-trigger-role">Operations reviewer</span>
        </span>
        <ChevronDown size={15} className="up-chevron" aria-hidden="true" />
      </button>

      <div id={menuId} className="up-menu-panel" hidden={!menuOpen}>
        <div className="up-menu-summary">
          <span className="up-avatar" aria-hidden="true">
            AM
          </span>
          <div className="up-menu-summary-text">
            <span className="up-menu-summary-name">Alex Morgan</span>
            <span className="up-menu-summary-meta">
              Operations · Case review
            </span>
            <span className="up-sample-badge">Demo profile</span>
          </div>
        </div>
        <hr className="up-menu-divider" />
        <div
          ref={menuListRef}
          className="up-menu-list"
          role="menu"
          aria-labelledby={triggerId}
          onKeyDown={handleMenuKeyDown}
        >
          <button
            type="button"
            role="menuitem"
            tabIndex={-1}
            className="up-menu-item"
            onClick={() => openDetail("profile")}
          >
            <span className="up-menu-item-icon" aria-hidden="true">
              <User size={16} />
            </span>
            <span className="up-menu-item-copy">
              <span className="up-menu-item-title">Profile</span>
              <span className="up-menu-item-hint">Name, team and role</span>
            </span>
          </button>
          <button
            type="button"
            role="menuitem"
            tabIndex={-1}
            className="up-menu-item"
            onClick={() => openDetail("permissions")}
          >
            <span className="up-menu-item-icon" aria-hidden="true">
              <ShieldCheck size={16} />
            </span>
            <span className="up-menu-item-copy">
              <span className="up-menu-item-title">
                Responsibilities &amp; permissions
              </span>
              <span className="up-menu-item-hint">
                Approval requirements and restrictions
              </span>
            </span>
          </button>
        </div>
      </div>

      {activeDetail !== null &&
        typeof document !== "undefined" &&
        createPortal(
          <dialog
            ref={dialogRef}
            className="up-dialog"
            aria-labelledby={dialogTitleId}
            onClose={handleDialogClose}
            onPointerDown={(e) => {
              const dialog = dialogRef.current;
              pressedBackdropRef.current =
                !!dialog && isOutsideDialog(e, dialog);
            }}
            onPointerUp={(e) => {
              const dialog = dialogRef.current;
              const wasOutside = pressedBackdropRef.current;
              pressedBackdropRef.current = false;
              if (wasOutside && dialog && isOutsideDialog(e, dialog)) {
                dialog.close();
              }
            }}
          >
            <div className="up-dialog-surface">
              <div className="up-dialog-header">
                <div className="up-dialog-heading-group">
                  {activeDetail === "profile" ? (
                    <span
                      className="up-avatar up-dialog-avatar"
                      aria-hidden="true"
                    >
                      AM
                    </span>
                  ) : (
                    <span className="up-dialog-icon-badge" aria-hidden="true">
                      <ShieldCheck size={20} />
                    </span>
                  )}
                  <div>
                    <h2 id={dialogTitleId} className="up-dialog-title">
                      {activeDetail === "profile"
                        ? "Alex Morgan"
                        : "Responsibilities & permissions"}
                    </h2>
                    <p className="up-dialog-subtitle">
                      {activeDetail === "profile"
                        ? "Operations reviewer · Demo profile"
                        : "Approval requirements and restrictions"}
                    </p>
                  </div>
                </div>
                <button
                  ref={closeBtnRef}
                  type="button"
                  className="up-dialog-close"
                  aria-label="Close dialog"
                  autoFocus
                  onClick={closeDetail}
                >
                  <X size={18} aria-hidden="true" />
                </button>
              </div>

              <div className="up-dialog-body">
                {activeDetail === "profile" ? (
                  <>
                    <dl className="up-meta-grid">
                      <div className="up-meta-card">
                        <dt>Name</dt>
                        <dd>Alex Morgan</dd>
                      </div>
                      <div className="up-meta-card">
                        <dt>Role</dt>
                        <dd>Operations reviewer</dd>
                      </div>
                      <div className="up-meta-card">
                        <dt>Department</dt>
                        <dd>Operations</dd>
                      </div>
                      <div className="up-meta-card">
                        <dt>Team</dt>
                        <dd>Case review</dd>
                      </div>
                    </dl>

                    <div className="up-section">
                      <h3 className="up-section-title">Responsibilities</h3>
                      <ul className="up-list">
                        <li>Review case findings and supporting evidence.</li>
                        <li>Check recommended next steps.</li>
                        <li>
                          Review eligible requests and record a decision note.
                        </li>
                        <li>Follow up with the relevant department owners.</li>
                      </ul>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="up-callout">
                      <Info
                        size={17}
                        className="up-callout-icon"
                        aria-hidden="true"
                      />
                      <p>
                        This demo profile is for display; approval rules apply
                        to every request.
                      </p>
                    </div>

                    <div className="up-section">
                      <h3 className="up-section-title">Eligibility</h3>
                      <ul className="up-list">
                        <li>
                          Pending requests become available once the review
                          finishes successfully and is not busy.
                        </li>
                        <li>
                          Required departmental reviews must be approved before
                          action requests can be decided.
                        </li>
                        <li>
                          A decision note is required before approving or
                          declining a request.
                        </li>
                        <li>
                          Saved replays are read-only and do not offer approval
                          actions.
                        </li>
                      </ul>
                    </div>

                    <div className="up-section">
                      <h3 className="up-section-title">Decision effects</h3>
                      <ul className="up-list">
                        <li>
                          Departmental approval records the decision and note
                          without making a business change.
                        </li>
                        <li>
                          Approving an eligible action request simulates that
                          specific proposed change.
                        </li>
                      </ul>
                    </div>

                    <div className="up-section">
                      <h3 className="up-section-title">Restrictions</h3>
                      <ul className="up-list">
                        <li>
                          Customer data disclosure, correction, and erasure
                          require current passed identity verification.
                        </li>
                        <li>
                          Active legal holds and retention schedules block
                          erasure even if approved.
                        </li>
                      </ul>
                    </div>
                  </>
                )}
              </div>

              <div className="up-dialog-footer">
                <button
                  type="button"
                  className="up-dialog-footer-btn"
                  onClick={closeDetail}
                >
                  Close
                </button>
              </div>
            </div>
          </dialog>,
          document.body,
        )}
    </div>
  );
}
