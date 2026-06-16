'use client';

/**
 * Login Page
 */

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Activity, Mail, Lock, User, AlertCircle, ArrowLeft } from 'lucide-react';
import { api } from '@/lib/api';
import styles from './page.module.css';

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (searchParams.get('register') === 'true') {
      setIsRegistering(true);
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      if (isRegistering) {
        await api.register(email, password, username || undefined);
      } else {
        await api.login(email, password);
      }
      router.push('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={styles.loginPage}>
      <div className={styles.loginContainer}>
        {/* Back Link */}
        <Link href="/" className={styles.backLink}>
          <ArrowLeft className={styles.backIcon} />
          Back to home
        </Link>

        {/* Logo */}
        <div className={styles.logoSection}>
          <div className={styles.logoBox}>
            <Activity className={styles.logoBoxIcon} />
          </div>
          <h1 className={styles.logoTitle}>Scanify</h1>
          <p className={styles.logoSubtitle}>
            {isRegistering ? 'Create your account' : 'Welcome back'}
          </p>
        </div>

        {/* Form */}
        <div className="card">
          {error && (
            <div className={styles.errorBox}>
              <AlertCircle className={styles.errorIcon} />
              <span className={styles.errorText}>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className={styles.form}>
            {isRegistering && (
              <div>
                <label className={styles.fieldLabel}>Username (optional)</label>
                <div className={styles.inputWrapper}>
                  <User className={styles.inputIcon} />
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className={`input ${styles.inputWithIcon}`}
                    placeholder="johndoe"
                  />
                </div>
              </div>
            )}

            <div>
              <label className={styles.fieldLabel}>Email</label>
              <div className={styles.inputWrapper}>
                <Mail className={styles.inputIcon} />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className={`input ${styles.inputWithIcon}`}
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
                  className={`input ${styles.inputWithIcon}`}
                  placeholder="&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;"
                  required
                  minLength={6}
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
                isRegistering ? 'Create Account' : 'Sign In'
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

        {/* Demo credentials */}
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
      </div>
    </div>
  );
}
