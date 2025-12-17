/**
 * Scanify Landing Page
 *
 * Marketing page with pricing and features.
 */

import Link from 'next/link';
import { Activity, Zap, Shield, BarChart3, Check, ArrowRight } from 'lucide-react';

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
    <div className="min-h-screen">
      {/* Navigation */}
      <nav className="border-b border-scanify-dark-700 bg-scanify-dark-900/80 backdrop-blur-sm fixed top-0 w-full z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16 items-center">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-scanify-primary to-scanify-secondary rounded-lg flex items-center justify-center">
                <Activity className="w-5 h-5 text-white" />
              </div>
              <span className="text-xl font-bold text-white">Scanify</span>
            </div>
            <div className="flex items-center gap-4">
              <Link href="/login" className="text-gray-400 hover:text-white transition-colors">
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
      <section className="pt-32 pb-20 px-4">
        <div className="max-w-7xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-scanify-dark-700 rounded-full px-4 py-1.5 mb-6">
            <Zap className="w-4 h-4 text-scanify-accent" />
            <span className="text-sm text-gray-300">ML-Powered Trading Signals</span>
          </div>
          <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
            Trade Smarter with
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-scanify-primary to-scanify-accent"> Scanify</span>
          </h1>
          <p className="text-xl text-gray-400 max-w-2xl mx-auto mb-8">
            Professional-grade market scanners powered by machine learning. Get real-time signals for momentum, breakouts, options flow, and more.
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link href="/login?register=true" className="btn-primary text-lg px-8 py-3 flex items-center gap-2">
              Start Free Trial <ArrowRight className="w-5 h-5" />
            </Link>
            <Link href="#pricing" className="btn-secondary text-lg px-8 py-3">
              View Pricing
            </Link>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-20 px-4 bg-scanify-dark-800/50">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl font-bold text-white text-center mb-12">
            Everything You Need to Trade Better
          </h2>
          <div className="grid md:grid-cols-3 gap-8">
            {features.map((feature) => (
              <div key={feature.title} className="card">
                <feature.icon className="w-10 h-10 text-scanify-primary mb-4" />
                <h3 className="text-xl font-semibold text-white mb-2">{feature.title}</h3>
                <p className="text-gray-400">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-20 px-4">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-3xl font-bold text-white text-center mb-4">
            Simple, Transparent Pricing
          </h2>
          <p className="text-gray-400 text-center mb-12 max-w-xl mx-auto">
            Start free and upgrade as you grow. No hidden fees, cancel anytime.
          </p>
          <div className="grid md:grid-cols-4 gap-6">
            {pricingTiers.map((tier) => (
              <div
                key={tier.name}
                className={`card relative ${
                  tier.popular ? 'border-scanify-primary ring-2 ring-scanify-primary/20' : ''
                }`}
              >
                {tier.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="bg-scanify-primary text-white text-xs font-bold px-3 py-1 rounded-full">
                      MOST POPULAR
                    </span>
                  </div>
                )}
                <h3 className="text-xl font-semibold text-white">{tier.name}</h3>
                <div className="mt-4 mb-2">
                  <span className="text-4xl font-bold text-white">${tier.price}</span>
                  <span className="text-gray-500">/month</span>
                </div>
                <p className="text-sm text-gray-400 mb-6">{tier.description}</p>
                <ul className="space-y-3 mb-6">
                  {tier.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2 text-sm">
                      <Check className="w-4 h-4 text-scanify-success flex-shrink-0 mt-0.5" />
                      <span className="text-gray-300">{feature}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  href={`/login?plan=${tier.name.toLowerCase()}`}
                  className={`block text-center py-2 rounded-lg font-medium transition-colors ${
                    tier.popular
                      ? 'bg-scanify-primary hover:bg-indigo-600 text-white'
                      : 'bg-scanify-dark-700 hover:bg-scanify-dark-600 text-gray-200'
                  }`}
                >
                  {tier.cta}
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 px-4 bg-gradient-to-r from-scanify-primary/20 to-scanify-secondary/20">
        <div className="max-w-3xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-white mb-4">
            Ready to Transform Your Trading?
          </h2>
          <p className="text-gray-400 mb-8">
            Join thousands of traders using Scanify to find better opportunities.
          </p>
          <Link href="/login?register=true" className="btn-primary text-lg px-8 py-3">
            Start Your Free Trial
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-8 px-4 border-t border-scanify-dark-700">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-scanify-primary" />
            <span className="text-gray-400">Scanify</span>
          </div>
          <p className="text-sm text-gray-500">
            © 2024 Scanify. All rights reserved.
          </p>
        </div>
      </footer>
    </div>
  );
}
