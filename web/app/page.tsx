/**
 * Scanify Landing Page
 *
 * Marketing page with pricing and features.
 */

import Link from 'next/link';
import { Activity, Zap, Shield, BarChart3, Check, ArrowRight } from 'lucide-react';
import styles from './page.module.css';

const features = [
  {
    icon: Zap,
    title: 'Real-Time Signals',
    description: 'Get instant trading signals from our ML-powered scanners the moment opportunities arise.',
  },
  {
    icon: BarChart3,
    title: '7 Scanner Types',
    description: 'Momentum, Breakout, Reversal, Options Flow, Squeeze, Gamma, and Multi-Timeframe analysis.',
  },
  {
    icon: Shield,
    title: 'Risk Management',
    description: 'Every signal includes entry, stop loss, and targets with calculated risk/reward ratios.',
  },
];

const pricingTiers = [
  {
    name: 'Free',
    price: 0,
    description: 'Get started with delayed signals',
    features: [
      '15-minute delayed signals',
      'Momentum scanner only',
      '5 symbols max',
      '60 API calls/hour',
    ],
    cta: 'Start Free',
    popular: false,
  },
  {
    name: 'Basic',
    price: 29,
    description: 'Essential tools for active traders',
    features: [
      '1-minute delayed signals',
      '3 scanner types',
      '25 symbols',
      'Email alerts',
      'Discord access',
    ],
    cta: 'Get Started',
    popular: false,
  },
  {
    name: 'Pro',
    price: 99,
    description: 'Real-time for serious traders',
    features: [
      'Real-time signals',
      'All 7 scanners',
      '100 symbols',
      'WebSocket streaming',
      'Custom alert rules',
      'Export data',
      '30-day history',
    ],
    cta: 'Go Pro',
    popular: true,
  },
  {
    name: 'Elite',
    price: 299,
    description: 'Maximum power & support',
    features: [
      'Everything in Pro',
      'Unlimited symbols',
      'API access',
      '365-day history',
      'Priority support',
      '1-on-1 calls',
    ],
    cta: 'Go Elite',
    popular: false,
  },
];

export default function LandingPage() {
  return (
    <div className={styles.landing}>
      {/* Navigation */}
      <nav className={styles.nav}>
        <div className={styles.navInner}>
          <div className={styles.navContent}>
            <div className={styles.logoGroup}>
              <div className={styles.logoIcon}>
                <Activity className={styles.logoIconImg} />
              </div>
              <span className={styles.logoText}>Scanify</span>
            </div>
            <div className={styles.navActions}>
              <Link href="/login" className={styles.signInLink}>
                Sign In
              </Link>
              <Link href="/login?register=true" className="btn-primary">
                Get Started
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.heroBadge}>
            <Zap className={styles.heroBadgeIcon} />
            <span className={styles.heroBadgeText}>ML-Powered Trading Signals</span>
          </div>
          <h1 className={styles.heroTitle}>
            Trade Smarter with
            <span className={styles.heroGradientText}> Scanify</span>
          </h1>
          <p className={styles.heroDescription}>
            Professional-grade market scanners powered by machine learning. Get real-time signals for momentum, breakouts, options flow, and more.
          </p>
          <div className={styles.heroCta}>
            <Link href="/login?register=true" className={`btn-primary ${styles.heroCtaPrimary}`}>
              Start Free Trial <ArrowRight className={styles.heroCtaPrimaryIcon} />
            </Link>
            <Link href="#pricing" className={`btn-secondary ${styles.heroCtaSecondary}`}>
              View Pricing
            </Link>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className={styles.features}>
        <div className={styles.featuresInner}>
          <h2 className={styles.featuresTitle}>
            Everything You Need to Trade Better
          </h2>
          <div className={styles.featuresGrid}>
            {features.map((feature) => (
              <div key={feature.title} className="card">
                <feature.icon className={styles.featureIcon} />
                <h3 className={styles.featureTitle}>{feature.title}</h3>
                <p className={styles.featureDescription}>{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className={styles.pricing}>
        <div className={styles.pricingInner}>
          <h2 className={styles.pricingTitle}>
            Simple, Transparent Pricing
          </h2>
          <p className={styles.pricingSubtitle}>
            Start free and upgrade as you grow. No hidden fees, cancel anytime.
          </p>
          <div className={styles.pricingGrid}>
            {pricingTiers.map((tier) => (
              <div
                key={tier.name}
                className={`card ${styles.pricingCard} ${tier.popular ? styles.pricingCardPopular : ''}`}
              >
                {tier.popular && (
                  <div className={styles.popularBadgeWrapper}>
                    <span className={styles.popularBadge}>
                      MOST POPULAR
                    </span>
                  </div>
                )}
                <h3 className={styles.tierName}>{tier.name}</h3>
                <div className={styles.tierPriceWrapper}>
                  <span className={styles.tierPrice}>${tier.price}</span>
                  <span className={styles.tierPeriod}>/month</span>
                </div>
                <p className={styles.tierDescription}>{tier.description}</p>
                <ul className={styles.tierFeatures}>
                  {tier.features.map((feature) => (
                    <li key={feature} className={styles.tierFeature}>
                      <Check className={styles.tierFeatureCheck} />
                      <span className={styles.tierFeatureText}>{feature}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  href={`/login?plan=${tier.name.toLowerCase()}`}
                  className={tier.popular ? styles.tierCtaPopular : styles.tierCtaDefault}
                >
                  {tier.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className={styles.cta}>
        <div className={styles.ctaInner}>
          <h2 className={styles.ctaTitle}>
            Ready to Transform Your Trading?
          </h2>
          <p className={styles.ctaDescription}>
            Join thousands of traders using Scanify to find better opportunities.
          </p>
          <Link href="/login?register=true" className={`btn-primary ${styles.ctaButton}`}>
            Start Your Free Trial
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className={styles.footer}>
        <div className={styles.footerInner}>
          <div className={styles.footerLogo}>
            <Activity className={styles.footerLogoIcon} />
            <span className={styles.footerLogoText}>Scanify</span>
          </div>
          <p className={styles.footerCopyright}>
            &copy; 2024 Scanify. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
