'use client';

import "bootstrap-icons/font/bootstrap-icons.css";
import { useState, useEffect } from 'react';
import SpeechRecognition, { useSpeechRecognition } from 'react-speech-recognition';

interface Product {
  name: string;
  description: string;
  img_url: string;
}

export default function SearchPage() {
  const [messages, setMessages] = useState<{ text: string; sender: 'user' | 'bot'; products?: Product[] }[]>([]);
  const {
    transcript,
    listening,
    resetTranscript,
    browserSupportsSpeechRecognition
  } = useSpeechRecognition();
  const [inputValue, setInputValue] = useState('');

  useEffect(() => {
    setInputValue(transcript);
  }, [transcript]);

  if (!browserSupportsSpeechRecognition) {
    return <span>Browser doesn't support speech recognition.</span>;
  }

  const handleSendMessage = async () => {
    if (inputValue.trim() !== '') {
      const newMessages = [...messages, { text: inputValue, sender: 'user' as 'user' }];
      setMessages(newMessages);
      setInputValue('');
      resetTranscript();

      try {
        const response = await fetch('http://localhost:8000/chat', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ text: inputValue }),
        });

        const data = await response.json();
        const botResponse = data.response;

        // Simple parsing of the bot response to extract product information
        const productRegex = /\*\*\s*(.*?):\*\*\s*([\s\S]*?)\n\s*\[(.*?)\]/g;
        let match;
        const products: Product[] = [];
        while ((match = productRegex.exec(botResponse)) !== null) {
          products.push({
            name: match[1].trim(),
            description: match[2].trim(),
            img_url: match[3].trim(),
          });
        }

        setMessages([...newMessages, { text: botResponse, sender: 'bot', products }]);
      } catch (error) {
        console.error("Error sending message:", error);
        setMessages([...newMessages, { text: "Sorry, something went wrong.", sender: 'bot' }]);
      }
    }
  };

  return (
    <div className="container-fluid vh-100 d-flex flex-column">
      <div className="row flex-grow-1">
        <div className="col-md-4 d-flex flex-column bg-light p-3">
          <div className="flex-grow-1 mb-3 overflow-auto">
            {messages.map((msg, index) => (
              <div key={index} className={`p-2 ${msg.sender === 'user' ? 'text-end' : 'text-start'}`}>
                <span className={`d-inline-block p-2 rounded ${msg.sender === 'user' ? 'bg-primary text-white' : 'bg-secondary text-white'}`}>
                  {msg.text}
                </span>
              </div>
            ))}
          </div>
          <div className="input-group mb-3">
            <input
              type="text"
              className="form-control"
              placeholder="What can we help you find?"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSendMessage()}
            />
            <button className="btn btn-primary" type="button" onClick={handleSendMessage}>Send</button>
          </div>
          <div>
            <p>Microphone: {listening ? 'on' : 'off'}</p>
            <button className="btn btn-secondary me-2" onClick={() => SpeechRecognition.startListening({ continuous: true })}>Start</button>
            <button className="btn btn-secondary me-2" onClick={SpeechRecognition.stopListening}>Stop</button>
            <button className="btn btn-secondary" onClick={resetTranscript}>Reset</button>
          </div>
        </div>
        <div className="col-md-8 p-3 overflow-auto">
          <div className="row">
            {messages.flatMap(msg => msg.products || []).map((product, index) => (
              <div key={index} className="col-md-4 mb-3">
                <div className="card h-100">
                  <img src={product.img_url} className="card-img-top" alt={product.name} />
                  <div className="card-body">
                    <h5 className="card-title">{product.name}</h5>
                    <p className="card-text">{product.description}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

