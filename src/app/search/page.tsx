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
  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [isSearching, setIsSearching] = useState(false);

  useEffect(() => {
    setInputValue(transcript);
  }, [transcript]);

  if (!browserSupportsSpeechRecognition) {
    return <span>Browser doesn't support speech recognition.</span>;
  }

  const [products, setProducts] = useState<Product[]>([]);

  const handleSendMessage = async () => {
    if (inputValue.trim() !== '') {
      const newMessages = [...messages, { text: inputValue, sender: 'user' as 'user' }];
      setMessages(newMessages);
      setIsSearching(true);

      const eventSource = new EventSource(`http://localhost:8000/chat?query=${inputValue}`);
      eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Received event:', data); // Debug logging
        
        if (data.type === 'log') {
          setLogs(prev => [...prev, data.data]);
        } else if (data.type === 'products') {
          // Products arrived immediately - update display
          console.log('Setting products:', data.data);
          setProducts(data.data || []);
          setIsSearching(false);
          setLogs(prev => [...prev, `Products received: ${data.data?.length || 0} items`]);
        } else if (data.type === 'final_text') {
          // Final intro text from agent
          console.log('Received final_text:', data.data);
          setMessages(prevMessages => {
            const newMessages = [...prevMessages, { text: data.data, sender: 'bot' }];
            console.log('Updated messages:', newMessages);
            return newMessages;
          });
          setIsSearching(false);
          setLogs(prev => [...prev, `Final text received: ${data.data}`]);
        } else if (data.type === 'result') {
          // Legacy fallback for old format
          console.log('Received legacy result:', data.data);
          const { intro_text, products } = data.data;
          setMessages(prevMessages => [...prevMessages, { text: intro_text, sender: 'bot', products }]);
          setProducts(products || []);
          setIsSearching(false);
        } else {
          console.log('Unknown event type:', data.type, data);
        }
      };
      eventSource.onerror = (error) => {
        setLogs(prev => [...prev, 'EventSource error: ' + error.toString()]);
        setIsSearching(false);
        eventSource.close();
      };

      setInputValue('');
      resetTranscript();
    }
  };

  return (
    <div className="container-fluid vh-100 d-flex flex-column" style={{ backgroundColor: '#121212', color: '#e0e0e0' }}>
      <div className="row flex-grow-1 position-relative overflow-hidden">
        {/* Left Panel: Chat Interface */}
        <div className="col-md-4 d-flex flex-column p-3 border-end" style={{ backgroundColor: '#1e1e1e', borderColor: '#333' }}>
          <div className="flex-grow-1 mb-3 overflow-auto">
            {messages.map((msg, index) => (
              <div key={index} className={`p-2 ${msg.sender === 'user' ? 'text-end' : 'text-start'}`}>
                <div className={`d-inline-block p-2 rounded ${msg.sender === 'user' ? 'bg-primary text-white' : ''}`} style={{ 
                  backgroundColor: msg.sender === 'bot' ? '#333' : '',
                  direction: 'ltr',
                  textAlign: 'left',
                  maxWidth: '80%'
                }}>
                  <strong>{msg.sender === 'user' ? 'You: ' : 'Gemini: '}</strong>
                  {msg.text}
                </div>
              </div>
            ))}
          </div>
          <div className="input-group mb-3">
            <input
              type="text"
              className="form-control bg-dark text-white border-secondary"
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

        {/* Right Panel: Product Display */}
        <div className="col-md-8 p-3 overflow-auto position-relative" style={{ height: '100vh' }}>
          {/* Loading Indicator */}
          {isSearching && (
            <div className="position-absolute top-0 start-0 w-100 h-100 d-flex justify-content-center align-items-center" style={{ backgroundColor: 'rgba(18, 18, 18, 0.8)', zIndex: 10 }}>
              <div className="text-center text-primary">
                <div className="spinner-border text-primary" role="status">
                  <span className="visually-hidden">Loading...</span>
                </div>
                <h5 className="mt-3">Searching for products...</h5>
              </div>
            </div>
          )}
          
          {/* Empty State */}
          {products.length === 0 && !isSearching ? (
            <div className="d-flex justify-content-center align-items-center h-100">
              <div className="text-center text-muted">
                <i className="bi bi-search" style={{ fontSize: '4rem' }}></i>
                <h4 className="mt-3">No products to display</h4>
                <p>Start a conversation to see product recommendations</p>
              </div>
            </div>
          ) : (
            <>
              {/* First Row: 1 large, 2 small vertical */}
              {products.length > 0 && (
            <div className="row">
              {/* Large Image */}
              <div className="col-md-6 mb-4">
                <div className="card text-white border" style={{ backgroundColor: '#2d2d30', borderColor: '#444', height: '400px' }}>
                  <img src={products[0].img_url} className="card-img h-100" alt={products[0].name} style={{ objectFit: 'cover' }} />
                  <div className="card-img-overlay d-flex flex-column justify-content-end" style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.8) 20%, transparent)'}}>
                    <h5 className="card-title">{products[0].name}</h5>
                  </div>
                </div>
              </div>
              {/* 2 Small Images (Vertical) */}
              {products.length > 1 && (
                <div className="col-md-6 mb-4">
                  <div className="row">
                    <div className="col-12 mb-4">
                      <div className="card text-white border" style={{ backgroundColor: '#2d2d30', borderColor: '#444', height: '188px' }}>
                        <img src={products[1].img_url} className="card-img h-100" alt={products[1].name} style={{ objectFit: 'cover' }} />
                        <div className="card-img-overlay d-flex flex-column justify-content-end" style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.8) 20%, transparent)'}}>
                          <h5 className="card-title">{products[1].name}</h5>
                        </div>
                      </div>
                    </div>
                    {products.length > 2 && (
                      <div className="col-12">
                        <div className="card text-white border" style={{ backgroundColor: '#2d2d30', borderColor: '#444', height: '188px' }}>
                          <img src={products[2].img_url} className="card-img h-100" alt={products[2].name} style={{ objectFit: 'cover' }} />
                          <div className="card-img-overlay d-flex flex-column justify-content-end" style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.8) 20%, transparent)'}}>
                            <h5 className="card-title">{products[2].name}</h5>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

              {/* Remainder of the images */}
              {products.length > 3 && (
                <div className="row">
                  {products.slice(3).map((product, index) => (
                    <div key={index} className="col-md-4 mb-4">
                      <div className="card text-white border" style={{ backgroundColor: '#2d2d30', borderColor: '#444', height: '250px' }}>
                        <img src={product.img_url} className="card-img h-100" alt={product.name} style={{ objectFit: 'cover' }} />
                        <div className="card-img-overlay d-flex flex-column justify-content-end" style={{ background: 'linear-gradient(to top, rgba(0,0,0,0.8) 20%, transparent)'}}>
                          <h5 className="card-title">{product.name}</h5>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Log Console Button */}
        <div className="position-absolute top-0 end-0 p-3" style={{ zIndex: 1060 }}>
          <button className="btn btn-info" onClick={() => setShowLogs(!showLogs)}>
            <i className="bi bi-info-circle"></i>
          </button>
        </div>

        {/* Log Console Panel */}
        <div className={`position-absolute top-0 end-0 h-100 p-3 ${showLogs ? 'd-block' : 'd-none'}`} style={{ width: '450px', zIndex: 1050, backgroundColor: '#1e1e1e', borderLeft: '1px solid #333', transition: 'transform 0.3s ease-in-out', transform: showLogs ? 'translateX(0)' : 'translateX(100%)' }}>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <h5 className="mb-0">Server Log Console</h5>
              <button type="button" className="btn-close btn-close-white" onClick={() => setShowLogs(false)}></button>
            </div>
            <div className="h-100 overflow-auto" style={{maxHeight: 'calc(100vh - 100px)'}}>
              <pre style={{ color: '#e0e0e0', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {logs.join('\n')}
              </pre>
            </div>
        </div>
      </div>
    </div>
  );
}