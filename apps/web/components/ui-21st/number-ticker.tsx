"use client";

/**
 * Component: NumberTicker
 * Author / Library: Magic UI (adapted from 21st.dev search "number ticker")
 * Source URL: https://21st.dev/s/number-ticker
 *
 * Restrained editorial presentation:
 * - Uses monospace font and tabular numerals
 * - Clean counting transition without bouncy physics
 */

import React, { useEffect, useState } from "react";

interface NumberTickerProps {
  value: number;
  direction?: "up" | "down";
  delay?: number;
  className?: string;
  decimals?: number;
}

export function NumberTicker({
  value,
  direction = "up",
  delay = 0,
  className = "",
  decimals = 0,
}: NumberTickerProps) {
  const [displayValue, setDisplayValue] = useState<number>(0);

  useEffect(() => {
    let start = 0;
    const end = value;
    const duration = 600;
    const startTime = performance.now();

    const animate = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // easeOutCubic
      const easeProgress = 1 - Math.pow(1 - progress, 3);
      const current = start + (end - start) * easeProgress;
      setDisplayValue(current);

      if (progress < 1) {
        requestAnimationFrame(animate);
      } else {
        setDisplayValue(end);
      }
    };

    const timer = setTimeout(() => {
      requestAnimationFrame(animate);
    }, delay);

    return () => clearTimeout(timer);
  }, [value, delay]);

  return (
    <span className={`tabular-nums font-mono font-medium ${className}`}>
      {displayValue.toFixed(decimals)}
    </span>
  );
}
