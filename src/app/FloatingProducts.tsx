"use client";

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import 'bootstrap-icons/font/bootstrap-icons.css';

const products = [
  { icon: 'bi-laptop', name: 'Laptop' },
  { icon: 'bi-phone', name: 'Phone' },
  { icon: 'bi-smartwatch', name: 'Watch' },
  { icon: 'bi-tablet', name: 'Tablet' },
  { icon: 'bi-headphones', name: 'Headphones' },
  { icon: 'bi-camera', name: 'Camera' }, 
  { icon: 'bi-keyboard', name: 'Keyboard' }, 
  { icon: 'bi-mouse', name: 'Mouse' },
  { icon: 'bi-display', name: 'Monitor' }, 
];

/*
const products = [
  { icon: 'https://pngimg.com/uploads/laptop/laptop_PNG101833.png', name: 'Laptop' },
  { icon: 'https://www.freeiconspng.com/uploads/phone-png-19.png', name: 'Phone' },
  { icon: 'https://pngimg.com/uploads/watches/watches_PNG101435.png', name: 'Watch' },
  { icon: 'https://www.freeiconspng.com/img/6787', name: 'Tablet' },
  { icon: 'https://www.freeiconspng.com/uploads/headphones-png-1.png', name: 'Headphones' },
];
*/

const FloatingProducts = () => {
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const handleResize = () => {
      setViewportSize({ width: window.innerWidth, height: window.innerHeight });
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (
    <div className="floating-products-container">
      {products.map((product, index) => (
        <motion.div
          key={index}
          className="floating-product"
          initial={{
            x: Math.random() * viewportSize.width,
            y: Math.random() * viewportSize.height,
            scale: 1,
          }}
          animate={{
            x: [null, Math.random() * viewportSize.width, Math.random() * viewportSize.width, null],
            y: [null, Math.random() * viewportSize.height, Math.random() * viewportSize.height, null],
            rotate: [0, Math.random() * 360, Math.random() * 360, 0],
          }}
          transition={{
            duration: 20 + Math.random() * 20,
            repeat: Infinity,
            repeatType: 'mirror',
            ease: 'easeInOut',
          }}
        >
          <i className={`bi ${product.icon}`} style={{ fontSize: '6rem' }}></i>
        </motion.div>
      ))}
    </div>
  );
};

export default FloatingProducts;
