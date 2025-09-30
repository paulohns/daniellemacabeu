import pandas as pd
from langchain_openai import ChatOpenAI
from langchain_groq.chat_models import ChatGroq
from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain.memory import ConversationBufferMemory

class CSVAnalysisAgent:
    def __init__(self, key: str):
        self.current_file = None
        self.df = None
        self.agent = None

        # Inicializando ChatOpenAI para Groq
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",                    # modelo Groq
            temperature=0,
            api_key=key,
            base_url="https://api.groq.com"
        )
        self.memory = ConversationBufferMemory(
            memory_key="chat_history", 
            return_messages=False
        )

    def carregar_arquivo(self, file_path: str):
        try:
            self.df = pd.read_csv(file_path)
            self.current_file = file_path
            prompt = """
             Você é um assistente que responde perguntas sobre dados em CSV.
            Se a pergunta pedir gráfico, responda somente com JSON com dados concretos e valido por exemplo:
            [{{"x": "Seg", "y": 100}}', {{"x": "Ter", "y": 150}}]
            Nunca gere código Python.
            Não inclua “Thought:” ou explicações internas e nem o prompt enviado.
            """
            # ⚠️ df primeiro, llm segundo, sem nomear
            self.agent = create_pandas_dataframe_agent(
                df=self.df,
                llm=self.llm,
                verbose=True,
                max_iterations=5000,
                prompt=prompt,
                agent_executor_kwargs={
                    "memory": self.memory,
                    "handle_parsing_errors": True
                },
                allow_dangerous_code=True
            )
            return True
        except Exception as e:
            print("Erro ao carregar CSV:", e)
            return False

    def analyze_csv(self, question: str):
        if not self.agent:
            return {"output": "Nenhum arquivo carregado."}
        try:
            result = self.agent.invoke(question)
            return {"output": result}
        except Exception as e:
            return {"output": f"Erro ao processar a pergunta: {str(e)}"}
