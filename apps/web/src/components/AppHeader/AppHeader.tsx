import React, { useState, useRef, useEffect } from "react";
import styles from "./AppHeader.module.css";

export interface NavItem {
  id: string;
  label: string;
  href: string;
}

const DEFAULT_NAV_ITEMS: NavItem[] = [
  { id: "examples", label: "Examples", href: "#examples" },
  { id: "how", label: "How it works", href: "#how" },
  { id: "developer", label: "For developers", href: "#developer" },
  { id: "source", label: "Source and limitations", href: "#source" },
];

export interface AppHeaderProps {
  navItems?: NavItem[];
  onNavigate?: (item: NavItem) => void;
  className?: string;
}

export function AppHeader({
  navItems = DEFAULT_NAV_ITEMS,
  onNavigate,
  className,
}: AppHeaderProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const toggleBtnRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);

  // Close mobile drawer on Escape and return focus
  useEffect(() => {
    if (!isMenuOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setIsMenuOpen(false);
        toggleBtnRef.current?.focus();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isMenuOpen]);

  const handleLinkClick = (item: NavItem, e: React.MouseEvent) => {
    setIsMenuOpen(false);
    if (onNavigate) {
      e.preventDefault();
      onNavigate(item);
    }
  };

  return (
    <header className={`${styles.header} ${className || ""}`} aria-label="Site header">
      <div className={styles.inner}>
        <a href="#top" className={styles.brand} aria-label="Inkflip: PDF reading inspector">
          <span className={styles.brandName}>Inkflip</span>
          <span className={styles.brandDescriptor}>PDF reading inspector</span>
        </a>

        {/* Desktop Navigation */}
        <nav role="navigation" aria-label="Main navigation" className={styles.desktopNav}>
          {navItems.map((item) => (
            <a
              key={item.id}
              href={item.href}
              className={styles.navLink}
              onClick={(e) => handleLinkClick(item, e)}
            >
              {item.label}
            </a>
          ))}
        </nav>

        {/* Mobile Navigation Toggle */}
        <button
          ref={toggleBtnRef}
          type="button"
          className={styles.mobileMenuBtn}
          aria-expanded={isMenuOpen}
          aria-controls="mobile-nav"
          aria-label="Toggle navigation menu"
          onClick={() => setIsMenuOpen((prev) => !prev)}
        >
          <span aria-hidden="true">{isMenuOpen ? "✕" : "☰"}</span>
        </button>

        {/* Mobile Navigation Drawer */}
        <nav
          ref={drawerRef}
          id="mobile-nav"
          role="navigation"
          aria-label="Mobile navigation"
          className={`${styles.mobileDrawer} ${isMenuOpen ? styles.mobileDrawerOpen : ""}`}
        >
          {navItems.map((item) => (
            <a
              key={item.id}
              href={item.href}
              className={styles.navLink}
              onClick={(e) => handleLinkClick(item, e)}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </div>
    </header>
  );
}

export default AppHeader;
