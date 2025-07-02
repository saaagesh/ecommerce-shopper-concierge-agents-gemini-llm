import Link from "next/link";
import "./HomePage.css";
import Aurora from "./AuroraClient";
import TrueFocus from './TrueFocus';
import FloatingProducts from './FloatingProducts';
import './FloatingProducts.css';

export default function HomePage() {
  return (
    <div className="container d-flex justify-content-center align-items-center vh-100">
      <Aurora />
      <FloatingProducts />
      <div className="text-center homepage-content">
        <div className="home-title">
          <TrueFocus 
            sentence="Shopper's Concierge"
            manualMode={false}
            blurAmount={5}
            borderColor="transparent"
            animationDuration={1}
            pauseBetweenAnimations={0.5}
          />
        </div>
        <p>Tailor your shopping experience with an AI concierge agent</p>
        <Link href="/search" className="btn btn-primary">
          Click to get started
        </Link>
      </div>
    </div>
  );
}

