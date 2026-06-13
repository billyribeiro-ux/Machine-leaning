/**
 * Login Component
 *
 * Authentication screen for the desktop app.
 */

import { useState } from 'react';
import { Activity, Mail, Lock, AlertCircle } from 'lucide-react';
import { useStore } from '../lib/store';
import styles from './Login.module.css';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);
  const { login, isLoading, error, clearError } = useStore();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();

    try {
      await login(email, password);
    } catch {
      // Error is handled in store
    }
  };

  return (
    <div className={styles.loginPage}>
      <div className={styles.loginContainer}>
        {/* Logo */}
        <div className={styles.logoSection}>
          <div className={styles.logoIcon}>
            <Activity className={styles.logoIconImg} />
          </div>
          <h1 className={styles.logoTitle}>Scanify</h1>
          <p className={styles.logoSubtitle}>Professional Trading Scanner</p>
        </div>

        {/* Login Form */}
        <div className="card">
          <h2 className={styles.formTitle}>
            {isRegistering ? 'Create Account' : 'Welcome Back'}
          </h2>

          {error && (
            <div className={styles.errorBox}>
              <AlertCircle className={styles.errorIcon} />
              <span className={styles.errorText}>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className={styles.form}>
            <div>
              <label className={styles.fieldLabel}>Email</label>
              <div className={styles.inputWrapper}>
                <Mail className={styles.inputIcon} />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={`input ${styles.inputField}`}
                  placeholder="you@example.com"
                  required
                />
              </div>
            </div>

            <div>
              <label className={styles.fieldLabel}>Password</label>
              <div className={styles.inputWrapper}>
                <Lock className={styles.inputIcon} />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={`input ${styles.inputField}`}
                  placeholder="••••••••"
                  required
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className={`btn-primary ${styles.submitButton}`}
            >
              {isLoading ? (
                <div className={styles.spinner} />
              ) : (
                <>
                  {isRegistering ? 'Create Account' : 'Sign In'}
                </>
              )}
            </button>
          </form>

          <div className={styles.toggleSection}>
            <button
              onClick={() => setIsRegistering(!isRegistering)}
              className={styles.toggleButton}
            >
              {isRegistering ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
            </button>
          </div>
        </div>

        {/* Demo Mode */}
        <div className={styles.demoSection}>
          <button
            onClick={() => {
              setEmail('demo@scanify.app');
              setPassword('demo123');
            }}
            className={styles.demoButton}
          >
            Use demo credentials
          </button>
        </div>

        {/* Footer */}
        <p className={styles.footer}>
          By signing in, you agree to our Terms of Service and Privacy Policy
        </p>
      </div>
    </div>
  );
}
