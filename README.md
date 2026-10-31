# StudyRAG 📚
### AI-Powered Learning & Research Assistant

StudyRAG is an AI-powered learning and research platform designed to make studying smarter, faster, and more interactive. It aims to combine Generative AI, Large Language Models (LLMs), and Retrieval-Augmented Generation (RAG) to help users interact with educational content and access relevant information efficiently.

---

## 🚀 Overview

StudyRAG aims to transform traditional learning into an intelligent, personalized experience by leveraging AI-driven information retrieval and knowledge assistance.

The platform is being developed with a focus on secure authentication, course management, and AI-powered learning capabilities.

## ✨ Key Features

- **User Authentication:** Secure account registration, email verification, login, and password recovery.
- **Course Management:** Create, access, and manage learning courses.
- **AI-Powered Assistance:** Intelligent learning support using Generative AI.
- **Retrieval-Augmented Generation (RAG):** Context-aware information retrieval and response generation.
- **Smart Document Interaction:** Designed to support learning from educational resources.
- **Secure Data Management:** PostgreSQL-backed data storage and user-specific access control.

## 🛠️ Tech Stack

| Category | Technologies |
|---|---|
| Frontend | React.js, TypeScript, Vite |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| AI/ML | Generative AI, LLMs, RAG |
| Email Service | Gmail SMTP |
| Version Control | Git, GitHub |
| Deployment | Vercel, Backend Hosting |

*Technologies listed should be adjusted to match the final implemented codebase.*

## 📂 Project Structure

```text
StudyRAG/
│
├── frontend/
│   ├── src/
│   ├── public/
│   └── package.json
│
├── backend/
│   ├── app/
│   ├── requirements.txt
│   └── main.py
│
├── .gitignore
├── README.md
└── LICENSE
```

## ⚙️ Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/StudyRAG.git
cd StudyRAG
```

### 2. Frontend Setup

```bash
cd frontend
npm install
```

Create a `.env` file using the required frontend environment variables.

Start the development server:

```bash
npm run dev
```

### 3. Backend Setup

Open another terminal:

```bash
cd backend
python -m venv venv
```

Activate the environment on Windows:

```powershell
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure the required environment variables before starting the backend.

Run FastAPI:

```bash
uvicorn main:app --reload
```

*Adjust the application import path if your FastAPI entry point is located elsewhere.*

## 🔐 Environment Variables

Never commit actual credentials or `.env` files to GitHub.

Configure the following variables in your local environment or deployment platform, using the exact names expected by your application.

| Variable | Purpose |
|---|---|
| `STUDYRAG_POSTGRES_URL` | PostgreSQL connection |
| `STUDYRAG_SMTP_URL` | SMTP email configuration |
| `FRONTEND_URL` | Frontend application URL |
| `SECRET_KEY` | Application security key |

## 🌐 Deployment

The planned deployment architecture:

- **Frontend:** Vercel
- **Backend:** Render or another compatible hosting provider
- **Database:** PostgreSQL
- **Email Service:** SMTP

Production deployment requires configuring public frontend/backend URLs, CORS, database connectivity, and email verification redirects.

## 🎯 Project Goals

- Make AI-assisted learning more accessible.
- Improve knowledge discovery and information retrieval.
- Enable context-aware educational assistance.
- Build a scalable and secure learning platform.
- Explore practical applications of Generative AI and RAG architectures.

## 🔮 Future Enhancements

- Advanced document ingestion and processing.
- Semantic search and vector database integration.
- Personalized AI learning recommendations.
- Interactive AI-generated quizzes.
- Conversation history and learning analytics.

## 🤝 Contributing

Contributions, suggestions, and feedback are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Commit your changes.
4. Submit a Pull Request.

## 📄 License

This project is currently under development. Licensing details will be added as the project progresses.

---

**StudyRAG — Learn Smarter. Research Better. Think Deeper.** 🚀
