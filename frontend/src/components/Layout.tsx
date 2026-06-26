// src/components/Layout.tsx
import React from 'react';
import './Layout.css';

interface LayoutProps {
  children: React.ReactNode;
  title: string;
  subtitle?: string;
}

const Layout: React.FC<LayoutProps> = ({ children, title, subtitle }) => {
  return (
    <div className="layout-root">
      <header className="layout-header">
        <div className="header-top-line">
          <span className="cross-motif"></span>
          <span className="header-subtitle">{subtitle || 'INITIATION'}</span>
        </div>
        <h1 className="layout-title">{title}</h1>
      </header>

      <main className="layout-main">
        {children}
      </main>
    </div>
  );
};

export default Layout;
