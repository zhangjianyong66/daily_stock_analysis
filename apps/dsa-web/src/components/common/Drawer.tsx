import type React from 'react';
import { useEffect, useCallback, useRef } from 'react';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';

let activeDrawerCount = 0;

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  dialogId?: string;
  width?: string;
  zIndex?: number;
  side?: 'left' | 'right';
  backdropClassName?: string;
}

/**
 * Side drawer component with terminal-inspired styling.
 */
export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  children,
  dialogId,
  width = 'max-w-2xl',
  zIndex = 50,
  side = 'right',
  backdropClassName,
}) => {
  const { t } = useUiLanguage();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onCloseRef.current();
        return;
      }
      if (e.key !== 'Tab') return;

      const dialog = dialogRef.current;
      if (!dialog) return;
      const focusableElements = Array.from(dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )).filter((element) => !element.hasAttribute('hidden'));

      if (focusableElements.length === 0) {
        e.preventDefault();
        dialog.focus();
        return;
      }

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      const activeElement = document.activeElement;
      if (e.shiftKey && (activeElement === firstElement || !dialog.contains(activeElement))) {
        e.preventDefault();
        lastElement.focus();
      } else if (!e.shiftKey && activeElement === lastElement) {
        e.preventDefault();
        firstElement.focus();
      }
    },
    []
  );

  useEffect(() => {
    if (isOpen) {
      const previouslyFocused = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
      document.addEventListener('keydown', handleKeyDown);
      activeDrawerCount++;
      if (activeDrawerCount === 1) {
        document.body.style.overflow = 'hidden';
      }
      closeButtonRef.current?.focus();

      return () => {
        document.removeEventListener('keydown', handleKeyDown);
        activeDrawerCount--;
        if (activeDrawerCount === 0) {
          document.body.style.overflow = '';
        }
        previouslyFocused?.focus();
      };
    }
  }, [isOpen, handleKeyDown]);

  if (!isOpen) return null;

  const titleId = title ? `drawer-title-${side}` : undefined;
  const drawerPositionClass = cn(
    'absolute inset-y-0 flex w-full',
    side === 'left' ? 'left-0 justify-start' : 'right-0 justify-end',
    width,
  );
  const borderClass = side === 'left' ? 'border-r' : 'border-l';
  const animationClass = side === 'left' ? 'animate-slide-in-left' : 'animate-slide-in-right';

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ zIndex }} role="presentation">
      {/* Backdrop */}
      <div
        className={cn(
          'absolute inset-0 bg-background/80 backdrop-blur-sm transition-opacity duration-300',
          backdropClassName,
        )}
        onClick={onClose}
      />

      <div className={drawerPositionClass}>
        <div
          ref={dialogRef}
          id={dialogId}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          tabIndex={-1}
          className={cn(
            'relative flex w-full flex-col bg-card',
            borderClass,
            side === 'right' ? 'border-border/80' : 'border-border/70 shadow-2xl',
            animationClass,
          )}
        >
          <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
            {title ? (
              <div>
                <span className="label-uppercase">DETAIL VIEW</span>
                <h2 id={titleId} className="mt-1 text-lg font-semibold text-foreground">{title}</h2>
              </div>
            ) : <div />}
            <button
              ref={closeButtonRef}
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-border/70 bg-card/80 text-secondary-text transition-colors hover:bg-hover hover:text-foreground"
              aria-label={t('common.closeDrawer')}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
};
