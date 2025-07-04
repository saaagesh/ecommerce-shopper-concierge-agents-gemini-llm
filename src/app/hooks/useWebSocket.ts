
"use client";
import { useState, useEffect, useRef } from 'react';

interface WebSocketHook {
  messages: any[];
  sendMessage: (message: string | ArrayBuffer) => void;
  logs: string[];
  isConnected: boolean;
}

export const useWebSocket = (url: string): WebSocketHook => {
  const [messages, setMessages] = useState<any[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const webSocketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (webSocketRef.current) {
      return;
    }

    const ws = new WebSocket(url);
    webSocketRef.current = ws;
    ws.binaryType = 'blob';

    ws.onopen = () => {
      console.log('WebSocket connection established');
      setIsConnected(true);
      setLogs(prev => [...prev, 'WebSocket connection established']);
    };

    ws.onmessage = (event) => {
      if (event.data instanceof Blob) {
        setMessages(prev => [...prev, event.data]);
      } else {
        const receivedMessage = JSON.parse(event.data);
        if (receivedMessage.type === 'log') {
          setLogs(prev => [...prev, receivedMessage.data]);
        } else {
          setMessages(prev => [...prev, receivedMessage]);
        }
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setLogs(prev => [...prev, 'WebSocket error: ' + error.toString()]);
    };

    ws.onclose = () => {
      console.log('WebSocket connection closed');
      setIsConnected(false);
      setLogs(prev => [...prev, 'WebSocket connection closed']);
      webSocketRef.current = null;
    };

    return () => {
      // This cleanup function will be called when the component unmounts.
      // In React's Strict Mode, it runs an extra time, which can cause issues.
      // The check for `webSocketRef.current` helps prevent premature closing.
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
      webSocketRef.current = null;
    };
  }, [url]);

  const sendMessage = (message: string | ArrayBuffer) => {
    if (webSocketRef.current && webSocketRef.current.readyState === WebSocket.OPEN) {
      webSocketRef.current.send(message);
    } else {
      console.error('WebSocket is not connected');
      setLogs(prev => [...prev, 'WebSocket is not connected']);
    }
  };

  return { messages, sendMessage, logs, isConnected };
};
