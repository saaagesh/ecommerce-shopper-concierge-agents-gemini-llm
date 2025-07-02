"use client";
import dynamic from "next/dynamic";

const AuroraComponent = dynamic(() => import("./Aurora"), { ssr: false });

const AuroraClient = () => {
  return <AuroraComponent />;
};

export default AuroraClient;
