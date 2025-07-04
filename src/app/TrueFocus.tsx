"use client";

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface TrueFocusProps {
  sentence: string;
  manualMode?: boolean;
  blurAmount?: number;
  borderColor?: string;
  animationDuration?: number;
  pauseBetweenAnimations?: number;
}

const TrueFocus: React.FC<TrueFocusProps> = ({
  sentence,
  manualMode = false,
  blurAmount = 5,
  borderColor = 'red',
  animationDuration = 0.5,
  pauseBetweenAnimations = 1,
}) => {
  const words = sentence.split(' ');
  const [focusedIndex, setFocusedIndex] = useState(0);

  useEffect(() => {
    if (!manualMode) {
      const interval = setInterval(() => {
        setFocusedIndex((prevIndex) => (prevIndex + 1) % words.length);
      }, (animationDuration + pauseBetweenAnimations) * 1000);

      return () => clearInterval(interval);
    }
  }, [manualMode, words.length, animationDuration, pauseBetweenAnimations]);

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
      {words.map((word, index) => (
        <motion.div
          key={index}
          style={{
            margin: '0 5px',
            padding: '5px 10px',
            border: '2px solid transparent',
            transition: `filter ${animationDuration}s, border-color ${animationDuration}s`,
          }}
          animate={{
            filter: `blur(${index === focusedIndex ? 0 : blurAmount}px)`,
            borderColor: index === focusedIndex ? borderColor : '#00000000',
          }}
          transition={{ duration: animationDuration }}
        >
          {word}
        </motion.div>
      ))}
    </div>
  );
};

export default TrueFocus;
