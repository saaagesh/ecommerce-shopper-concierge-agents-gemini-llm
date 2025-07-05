# Shoppers Concierge Frontend

A modern e-commerce search and recommendation system powered by Google's Gemini AI, featuring both text-based and real-time audio interactions with immediate product discovery.

## 🌟 Features

### 🔍 **Text-Based Search**
- **Natural Language Processing**: Search using conversational queries like "gifts for a 10-year-old" or "red mugs"
- **Immediate Results**: Products display instantly as they're found, no waiting for AI completion
- **Smart Research**: Automatic query expansion for broad searches using dedicated research agent
- **Real-time Streaming**: Server-sent events provide live updates and detailed logging

### 🎤 **Live Audio Chat**
- **Voice Interaction**: Natural voice conversations with Gemini AI
- **Real-time Tool Execution**: Products appear immediately when found, separate from speech
- **Audio Transcription**: Both user and AI responses displayed in chat interface
- **Bidirectional Streaming**: Simultaneous audio input/output with WebSocket connection

### 🛍️ **Product Discovery**
- **Vector Search Integration**: Powered by advanced similarity search across 3M+ products
- **Visual Product Grid**: Responsive layout with large hero images and grid display
- **Rich Product Data**: Names, descriptions, images, and direct links
- **Smart Categorization**: Automatic product type detection and organization

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Frontend      │    │    Backend       │    │  External APIs  │
│   (Next.js)     │◄──►│   (FastAPI +     │◄──►│                 │
│                 │    │    WebSocket)    │    │  • Vector Search│
│  • Text Search  │    │                  │    │  • Google Gemini│
│  • Audio Chat   │    │  • Text API      │    │  • Google Search│
│  • Product UI   │    │  • WebSocket     │    │                 │
└─────────────────┘    │  • Tool Agents   │    └─────────────────┘
                       └──────────────────┘
```

## 📁 Project Structure

### **Backend (`/backend/`)**

#### 🚀 **Core Servers**
- **`main.py`** - FastAPI server for text-based search with streaming responses
- **`audio_server.py`** - WebSocket server for real-time audio interactions
- **`audio_common.py`** - Base WebSocket server class and common utilities

#### 🛠️ **Shared Components**
- **`shared_tools.py`** - AI tools and product search functions used by both servers
- **`config.py`** - Configuration settings and environment variables
- **`requirements.txt`** - Python dependencies

### **Frontend (`/src/app/`)**

#### 📱 **Pages**
- **`page.tsx`** - Landing page with animated Aurora background and product showcase
- **`search/page.tsx`** - Text-based search interface with speech recognition
- **`live/page.tsx`** - Live audio chat interface with real-time product display

#### 🧩 **Components**
- **`components/LiveChat.tsx`** - WebSocket audio chat component with embedded AudioClient
- **`AuroraClient.tsx`** - Client wrapper for WebGL Aurora background effect
- **`Aurora.js`** - WebGL shader-based Aurora animation
- **`TrueFocus.tsx`** - Animated text focus effect for homepage
- **`FloatingProducts.tsx`** - Floating product icons animation

#### 🎨 **Styles**
- **`globals.css`** - Global styles and Bootstrap integration
- **`HomePage.css`** - Landing page specific styles
- **`Aurora.css`** - Aurora component styles
- **`FloatingProducts.css`** - Floating products animation styles

## 🚀 Quick Start

### Prerequisites
- **Python 3.13+**
- **Node.js 18+**
- **Google API Key** (Gemini AI)

### 1. Environment Setup

```bash
# Clone the repository
git clone <repository-url>
cd shoppers-concierge-frontend

# Create Python virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
cd backend
pip install -r requirements.txt

# Install Node.js dependencies
cd ..
npm install
```

### 2. Configuration

Create a `.env` file in the `/backend/` directory:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
VECTOR_SEARCH_URL=your_vector_search_endpoint
APP_NAME=shoppers_concierge
USER_ID=user_001
```

### 3. Start the Servers

```bash
# Terminal 1: Start the text API server
cd backend
python main.py
# Server runs on http://localhost:8000

# Terminal 2: Start the WebSocket server
cd backend  
python audio_server.py
# Server runs on ws://localhost:8765

# Terminal 3: Start the frontend
npm run dev
# Frontend runs on http://localhost:3000
```

### 4. Access the Application

- **Homepage**: http://localhost:3000
- **Text Search**: http://localhost:3000/search
- **Live Audio Chat**: http://localhost:3000/live

## 🔧 API Endpoints

### Text API Server (Port 8000)
- **`GET /chat?query={query}`** - Streaming text search with Server-Sent Events

### WebSocket Server (Port 8765)
- **WebSocket connection** - Real-time audio streaming and tool execution

## 🧠 AI Agents & Tools

### **Shopping Agent**
- **Model**: Gemini 2.5 Flash
- **Purpose**: Main conversational agent for product discovery
- **Tools**: Research Agent, Product Search

### **Research Agent** 
- **Model**: Gemini 1.5 Flash
- **Purpose**: Query expansion for broad searches
- **Tools**: Google Search API

### **Core Tools**
- **`find_shopping_items`** - Vector search across product database
- **`research_agent_tool`** - Intelligent query generation for complex requests

## 🎛️ Key Features Implementation

### **Immediate Product Display**
- Products stream to frontend immediately when found
- WebSocket events separate tool execution from speech generation
- Server-sent events provide real-time updates for text searches

### **Smart Response Filtering**
- AI responses filtered to prevent reading raw JSON data
- Tool outputs replaced with friendly conversational responses
- Duplicate execution prevention with unique ID tracking

### **Audio Processing**
- Bidirectional audio streaming with 16kHz PCM encoding
- Real-time transcription for both user input and AI responses
- Audio playback queue management for smooth conversation flow

### **Visual Experience**
- Responsive product grid with large hero images
- Dark theme optimized for product showcase
- Loading states and empty state illustrations
- Real-time server logs with collapsible debug console

## 🐛 Debugging & Monitoring

### **Server Logs**
Both text and audio servers provide detailed logging accessible via the frontend info panel:
- Tool execution tracking
- Product extraction and streaming
- WebSocket connection status
- Error handling and recovery

### **Frontend Debug**
- Browser console logs for WebSocket events
- Real-time server log display
- Network request monitoring via browser dev tools

## 🚀 Deployment Considerations

### **Environment Variables**
- Set `GOOGLE_API_KEY` for Gemini AI access
- Configure `VECTOR_SEARCH_URL` for product database
- Adjust `APP_NAME` and `USER_ID` for multi-tenant usage

### **Performance Optimization**
- Vector search results cached and optimized
- Audio streaming with efficient binary encoding
- React state management optimized for real-time updates

### **Security**
- API keys stored in environment variables
- CORS configured for frontend-backend communication
- WebSocket connections with proper error handling

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the Apache License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Check the server logs via the info panel in the frontend
- Review browser console for client-side debugging
- Ensure all environment variables are properly configured
- Verify WebSocket and HTTP server connectivity

---

*Built with ❤️ using Google Gemini AI, Next.js, FastAPI, and modern web technologies*