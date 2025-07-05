"use client";
import "bootstrap-icons/font/bootstrap-icons.css";
import { useState, useEffect, useRef } from 'react';

// This is a direct translation of the sample audio client, with added product handling.
class AudioClient {
    serverUrl: string;
    ws: WebSocket | null;
    audioContext: AudioContext | null;
    recorder: { source: MediaStreamAudioSourceNode; processor: ScriptProcessorNode; stream: MediaStream } | null;
    isRecording: boolean;
    isConnected: boolean;
    onReady: () => void;
    onAudioReceived: (data: any) => void;
    onTextReceived: (text: string, isUser: boolean) => void;
    onProductsReceived: (products: any[]) => void;
    onLogReceived: (log: string) => void;
    onTurnComplete: () => void;
    onBotSpeechStart: () => void;
    onBotSpeechEnd: () => void;
    onError: (error: any) => void;
    audioQueue: ArrayBuffer[];
    isPlaying: boolean;

    constructor(serverUrl = 'ws://localhost:8765') {
        this.serverUrl = serverUrl;
        this.ws = null;
        this.audioContext = null;
        this.recorder = null;
        this.isRecording = false;
        this.isConnected = false;

        // Callbacks
        this.onReady = () => {};
        this.onAudioReceived = (data) => {};
        this.onTextReceived = (text, isUser) => {};
        this.onProductsReceived = (products) => {};
        this.onLogReceived = (log) => {};
        this.onTurnComplete = () => {};
        this.onBotSpeechStart = () => {};
        this.onBotSpeechEnd = () => {};
        this.onError = (error) => {};

        // Audio playback queue
        this.audioQueue = [];
        this.isPlaying = false;
    }

    async connect() {
        return new Promise<void>((resolve, reject) => {
            this.ws = new WebSocket(this.serverUrl);
            this.ws.onopen = () => {
                this.isConnected = true;
                this.onReady();
                resolve();
            };
            this.ws.onmessage = (event) => {
                const message = JSON.parse(event.data);
                switch (message.type) {
                    case 'audio':
                        this.onAudioReceived(message.data);
                        this.playAudio(message.data);
                        break;
                    case 'text':
                        this.onTextReceived(message.data, false); // Bot text is always false
                        break;
                    case 'user_text':
                        this.onTextReceived(message.data, true); // User text is always true  
                        break;
                    case 'products':
                        this.onProductsReceived(message.data);
                        break;
                    case 'log':
                        this.onLogReceived(message.data);
                        break;
                    case 'turn_complete':
                        this.onTurnComplete();
                        break;
                    case 'bot_speech_start':
                        this.onBotSpeechStart();
                        break;
                    case 'bot_speech_end':
                        this.onBotSpeechEnd();
                        break;
                }
            };
            this.ws.onerror = (error) => {
                console.error('WebSocket Error:', error);
                this.onError(error);
            };
            this.ws.onclose = () => {
                this.isConnected = false;
                console.log('WebSocket connection closed');
            };
        });
    }

    async initializeAudio() {
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
        }
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const source = this.audioContext.createMediaStreamSource(stream);
        const processor = this.audioContext.createScriptProcessor(4096, 1, 1);
        processor.onaudioprocess = (e) => {
            if (!this.isRecording) return;
            const inputData = e.inputBuffer.getChannelData(0);
            const int16Data = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                int16Data[i] = Math.max(-32768, Math.min(32767, Math.floor(inputData[i] * 32768)));
            }
            if (this.isConnected && this.ws) {
                const audioBuffer = new Uint8Array(int16Data.buffer);
                const base64Audio = this._arrayBufferToBase64(audioBuffer.buffer);
                this.ws.send(JSON.stringify({ type: 'audio', data: base64Audio }));
            }
        };
        source.connect(processor);
        processor.connect(this.audioContext.destination);
        this.recorder = { source, processor, stream };
    }

    async startRecording() {
        if (!this.recorder) await this.initializeAudio();
        this.isRecording = true;
    }

    stopRecording() {
        this.isRecording = false;
    }

    playAudio(base64Audio: string) {
        const audioData = this._base64ToArrayBuffer(base64Audio);
        this.audioQueue.push(audioData);
        if (!this.isPlaying) this.playNextInQueue();
    }

    playNextInQueue() {
        if (this.audioQueue.length === 0 || !this.audioContext) {
            this.isPlaying = false;
            return;
        }
        this.isPlaying = true;
        const audioData = this.audioQueue.shift();
        if (!audioData) {
            this.playNextInQueue();
            return;
        }
        const int16Array = new Int16Array(audioData);
        const float32Array = new Float32Array(int16Array.length);
        for (let i = 0; i < int16Array.length; i++) {
            float32Array[i] = int16Array[i] / 32768.0;
        }
        const audioBuffer = this.audioContext.createBuffer(1, float32Array.length, 24000); // Use 24000 for output sample rate
        audioBuffer.getChannelData(0).set(float32Array);
        const source = this.audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.audioContext.destination);
        source.onended = () => {
            this.isPlaying = false;
            this.playNextInQueue();
        };
        source.start(0);
    }

    close() {
        this.isRecording = false;
        if (this.recorder) {
            this.recorder.stream.getTracks().forEach(track => track.stop());
            this.recorder.source.disconnect();
            this.recorder.processor.disconnect();
        }
        if (this.ws) this.ws.close();
    }

    _arrayBufferToBase64(buffer: ArrayBuffer): string {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
        return btoa(binary);
    }

    _base64ToArrayBuffer(base64: string): ArrayBuffer {
        const binaryString = atob(base64);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) bytes[i] = binaryString.charCodeAt(i);
        return bytes.buffer;
    }
}

export default function LiveChat() {
    const [messages, setMessages] = useState<{ text: string; sender: 'user' | 'bot' }[]>([]);
    const [products, setProducts] = useState<any[]>([]);
    const [isRecording, setIsRecording] = useState(false);
    const [isSearching, setIsSearching] = useState(false);
    const audioClientRef = useRef<AudioClient | null>(null);
    const messagesEndRef = useRef<HTMLDivElement | null>(null);
    const isBotSpeaking = useRef(false);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(scrollToBottom, [messages]);

    const [debugInfo, setDebugInfo] = useState<string>('');
    const [showLogs, setShowLogs] = useState(false);
    const [logs, setLogs] = useState<string[]>([]);

    useEffect(() => {
        audioClientRef.current = new AudioClient('ws://localhost:8765');
        audioClientRef.current.onReady = () => {
            console.log('Audio client ready');
            setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] WebSocket connection established.`]);
        };
        
        audioClientRef.current.onBotSpeechStart = () => {
            isBotSpeaking.current = true;
            setMessages(prev => [...prev, { text: "", sender: 'bot' }]);
        };

        audioClientRef.current.onTextReceived = (text, isUser) => {
            setMessages(prev => {
                const lastMessage = prev[prev.length - 1];
                if (isUser) {
                    // If the last message was from the user, append to it. Otherwise, create a new message.
                    if (lastMessage && lastMessage.sender === 'user') {
                        const updatedMessages = [...prev];
                        updatedMessages[updatedMessages.length - 1] = { ...lastMessage, text: lastMessage.text + text };
                        return updatedMessages;
                    }
                    return [...prev, { text, sender: 'user' }];
                }
                
                // For bot messages, append if the bot is speaking.
                if (isBotSpeaking.current && lastMessage && lastMessage.sender === 'bot') {
                    const updatedMessages = [...prev];
                    updatedMessages[updatedMessages.length - 1] = { ...lastMessage, text: lastMessage.text + text };
                    return updatedMessages;
                }
                
                return [...prev, { text, sender: 'bot' }];
            });
        };

        audioClientRef.current.onBotSpeechEnd = () => {
            isBotSpeaking.current = false;
        };

        audioClientRef.current.onProductsReceived = (newProducts) => {
            console.log("PRODUCTS RECEIVED ON FRONTEND:", newProducts);
            setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] PRODUCTS RECEIVED: ${newProducts.length} items - RENDERING IMMEDIATELY`]);
            // Render products immediately when received, don't wait for speech completion
            setProducts(newProducts || []);
        };

        audioClientRef.current.onLogReceived = (logMessage) => {
            setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${logMessage}`]);
            
            // Track search progress
            if (logMessage.includes("TOOL EXECUTION DETECTED: find_shopping_items")) {
                setIsSearching(true);
                setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] SEARCH STARTED - Loading products...`]);
            } else if (logMessage.includes("PRODUCTS SENT SUCCESSFULLY")) {
                setIsSearching(false);
                setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] SEARCH COMPLETED - Products displayed`]);
            }
        };

        audioClientRef.current.onError = (error) => {
            console.error("WebSocket Error:", error);
            setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] WebSocket Error: ${JSON.stringify(error)}`]);
        };

        audioClientRef.current.connect().catch(error => {
            console.error("Connection failed:", error);
            setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Connection failed: ${error}`]);
        });

        return () => {
            audioClientRef.current?.close();
            setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] WebSocket connection closed.`]);
        };
    }, []);

    const handleStartRecording = async () => {
        if (audioClientRef.current) {
            // Don't clear products immediately - let them stay until new results come in
            setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Started recording - keeping previous results until new search completes`]);
            await audioClientRef.current.startRecording();
            setIsRecording(true);
        }
    };

    const handleStopRecording = () => {
        if (audioClientRef.current) {
            audioClientRef.current.stopRecording();
            setIsRecording(false);
            setLogs(prev => [...prev, `[${new Date().toLocaleTimeString()}] Stopped recording`]);
        }
    };

    const clearLogs = () => {
        setLogs([]);
    };

    return (
        <div className="container-fluid vh-100 d-flex flex-column" style={{ backgroundColor: '#121212', color: '#e0e0e0' }}>
            <div className="row flex-grow-1 position-relative overflow-hidden">
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
                        <div ref={messagesEndRef} />
                    </div>
                    <div className="d-flex justify-content-center align-items-center">
                        <button
                            className={`btn ${isRecording ? 'btn-danger' : 'btn-primary'}`}
                            onMouseDown={handleStartRecording}
                            onMouseUp={handleStopRecording}
                            onTouchStart={handleStartRecording}
                            onTouchEnd={handleStopRecording}
                        >
                            {isRecording ? 'Recording...' : 'Push to Talk'}
                        </button>
                    </div>
                </div>
                {/* Product Display */}
                <div className="col-md-8 p-3 overflow-auto position-relative" style={{ height: '100vh' }}>
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
                    {products.length === 0 ? (
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
