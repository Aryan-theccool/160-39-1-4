'use client';

import { useEffect, useRef } from 'react';
import Link from 'next/link';
import gsap from 'gsap';
import { useGSAP } from '@gsap/react';
import ScrollToPlugin from 'gsap/ScrollToPlugin';

gsap.registerPlugin(useGSAP, ScrollToPlugin);

const AnimatedBackground = () => {
  const containerRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!containerRef.current) return;

    // Animated particles/cubes
    const createParticle = () => {
      const particle = document.createElement('div');
      particle.className = 'absolute rounded-full bg-gradient-to-r from-blue-400 to-indigo-600 opacity-20';
      const size = Math.random() * 100 + 20;
      particle.style.width = `${size}px`;
      particle.style.height = `${size}px`;
      particle.style.left = `${Math.random() * 100}%`;
      particle.style.top = `${Math.random() * 100}%`;
      particle.style.filter = 'blur(40px)';
      
      containerRef.current?.appendChild(particle);

      gsap.to(particle, {
        duration: Math.random() * 20 + 10,
        x: (Math.random() - 0.5) * 200,
        y: (Math.random() - 0.5) * 200,
        opacity: Math.random() * 0.5,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
      });

      return particle;
    };

    // Create multiple particles
    for (let i = 0; i < 6; i++) {
      createParticle();
    }
  }, { scope: containerRef });

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 overflow-hidden bg-gradient-to-br from-slate-950 via-blue-950 to-slate-950 -z-10"
    />
  );
};

const FloatingCard = ({ children, delay }: { children: React.ReactNode; delay: number }) => {
  const cardRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    gsap.from(cardRef.current, {
      opacity: 0,
      y: 50,
      duration: 0.8,
      delay,
      ease: 'power3.out',
    });

    gsap.to(cardRef.current, {
      y: -20,
      duration: 3,
      repeat: -1,
      yoyo: true,
      ease: 'sine.inOut',
      delay,
    });
  }, { scope: cardRef });

  return (
    <div ref={cardRef} className="relative">
      {children}
    </div>
  );
};

export default function Home() {
  const titleRef = useRef<HTMLDivElement>(null);
  const heroRef = useRef<HTMLDivElement>(null);
  const featuresRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    // Stagger title animation
    const titleChars = titleRef.current?.querySelectorAll('.char');
    if (titleChars) {
      gsap.from(titleChars, {
        opacity: 0,
        y: 20,
        duration: 0.6,
        stagger: 0.05,
        ease: 'power2.out',
      });
    }

    // Button animation
    const buttons = heroRef.current?.querySelectorAll('button, a');
    if (buttons) {
      gsap.from(buttons, {
        opacity: 0,
        scale: 0.8,
        duration: 0.6,
        stagger: 0.1,
        delay: 0.5,
        ease: 'back.out',
      });
    }

    // Feature cards on scroll
    ScrollToPlugin.defaults({ overwrite: 'auto' });
  }, { scope: heroRef });

  return (
    <div className="min-h-screen bg-slate-950 text-white overflow-hidden">
      <AnimatedBackground />

      {/* Navigation */}
      <nav className="fixed top-0 w-full z-50 backdrop-blur-md bg-slate-950/50 border-b border-blue-500/20">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center">
          <div className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent">
            BIS Standards AI
          </div>
          <div className="space-x-6">
            <Link href="/search" className="hover:text-blue-400 transition-colors">
              Search
            </Link>
            <Link href="/product" className="hover:text-blue-400 transition-colors">
              Product Finder
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section ref={heroRef} className="relative min-h-screen flex flex-col items-center justify-center px-4 pt-20">
        {/* Animated title */}
        <div ref={titleRef} className="text-center mb-12">
          <h1 className="text-6xl md:text-7xl font-black mb-6">
            <span className="char inline-block">I</span>
            <span className="char inline-block">n</span>
            <span className="char inline-block">d</span>
            <span className="char inline-block">i</span>
            <span className="char inline-block">a</span>
            <span className="char inline-block">'</span>
            <span className="char inline-block">s</span>
            <span className="char inline-block"> </span>
            <span className="char inline-block bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent">
              Standards
            </span>
            <span className="char inline-block"> </span>
            <span className="char inline-block bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              AI Engine
            </span>
          </h1>
          <p className="text-xl text-gray-300 max-w-2xl mx-auto mb-8">
            Discover applicable Indian Standards instantly. Powered by AI, verified by data.
          </p>
        </div>

        {/* CTA Buttons */}
        <div className="flex flex-wrap gap-6 justify-center mb-20">
          <Link
            href="/product"
            className="px-8 py-4 bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 rounded-lg font-semibold transition-all duration-300 transform hover:scale-105 shadow-lg hover:shadow-blue-500/50"
          >
            Find Standards
          </Link>
          <Link
            href="/search"
            className="px-8 py-4 border-2 border-indigo-500 hover:bg-indigo-500/10 rounded-lg font-semibold transition-all duration-300"
          >
            Search Database
          </Link>
        </div>

        {/* Stats Section */}
        <div className="grid grid-cols-3 gap-8 max-w-2xl">
          <FloatingCard delay={0.2}>
            <div className="text-center p-4 bg-blue-500/10 rounded-lg border border-blue-500/30 backdrop-blur-sm hover:bg-blue-500/20 transition-all">
              <div className="text-4xl font-bold text-blue-400">1,334</div>
              <div className="text-sm text-gray-400 mt-2">Standards Indexed</div>
            </div>
          </FloatingCard>
          <FloatingCard delay={0.4}>
            <div className="text-center p-4 bg-indigo-500/10 rounded-lg border border-indigo-500/30 backdrop-blur-sm hover:bg-indigo-500/20 transition-all">
              <div className="text-4xl font-bold text-indigo-400">100%</div>
              <div className="text-sm text-gray-400 mt-2">Verified Data</div>
            </div>
          </FloatingCard>
          <FloatingCard delay={0.6}>
            <div className="text-center p-4 bg-cyan-500/10 rounded-lg border border-cyan-500/30 backdrop-blur-sm hover:bg-cyan-500/20 transition-all">
              <div className="text-4xl font-bold text-cyan-400">AI-Powered</div>
              <div className="text-sm text-gray-400 mt-2">Smart Matching</div>
            </div>
          </FloatingCard>
        </div>
      </section>

      {/* Features Section */}
      <section ref={featuresRef} className="relative py-24 px-4">
        <div className="container mx-auto max-w-5xl">
          <h2 className="text-5xl font-bold text-center mb-16">
            Powerful Features
          </h2>

          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: '🔍',
                title: 'Smart Search',
                desc: 'Find standards by product description, not just by code.',
              },
              {
                icon: '⚡',
                title: 'Instant Matching',
                desc: 'AI-powered semantic search finds relevant standards instantly.',
              },
              {
                icon: '📊',
                title: 'Compliance Check',
                desc: 'Verify your products against mandatory QCO standards.',
              },
              {
                icon: '📥',
                title: 'Export Results',
                desc: 'Download standards list as CSV for your records.',
              },
              {
                icon: '🎯',
                title: 'Accurate Results',
                desc: '20/20 golden cases passing - rock-solid accuracy.',
              },
              {
                icon: '🚀',
                title: 'Fast & Reliable',
                desc: 'Deterministic results - same input, always same output.',
              },
            ].map((feature, i) => (
              <FloatingCard key={i} delay={0.1 + i * 0.15}>
                <div className="p-6 bg-gradient-to-br from-blue-500/10 to-indigo-500/10 rounded-xl border border-blue-500/30 hover:border-blue-500/60 transition-all duration-300 h-full group hover:scale-105 hover:shadow-lg hover:shadow-blue-500/20">
                  <div className="text-4xl mb-4 group-hover:scale-125 transition-transform duration-300">
                    {feature.icon}
                  </div>
                  <h3 className="text-xl font-bold mb-2">{feature.title}</h3>
                  <p className="text-gray-400">{feature.desc}</p>
                </div>
              </FloatingCard>
            ))}
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative py-24 px-4">
        <div className="container mx-auto max-w-3xl text-center">
          <h2 className="text-4xl font-bold mb-6">Ready to find your standards?</h2>
          <p className="text-xl text-gray-400 mb-10">
            Start discovering applicable Indian Standards for your products in seconds.
          </p>
          <Link
            href="/product"
            className="inline-block px-10 py-5 bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 rounded-lg font-bold text-lg transition-all duration-300 transform hover:scale-105 shadow-lg hover:shadow-blue-500/50"
          >
            Get Started Now
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-blue-500/20 py-8 px-4">
        <div className="container mx-auto text-center text-gray-400">
          <p>Built for SIH 26108 - Ministry of Consumer Affairs, Government of India</p>
          <p className="text-sm mt-2">Real Indian Standards. No Synthetic Data. 100% Verified.</p>
        </div>
      </footer>
    </div>
  );
}
