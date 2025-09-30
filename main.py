from io import BytesIO
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from agent import CSVAnalysisAgent

import json
import matplotlib.pyplot as plt
import pandas as pd
import os
import shutil
import io
import re

# Load environment variables from the .env file
load_dotenv()

# Criar pasta para arquivos se não existir
if not os.path.exists("files"):
    os.makedirs("files")

# Inicializar agente com Groq API Key
api_key = os.getenv('GROQ_API_KEY')

agent = CSVAnalysisAgent(key=api_key)

api_front_url = os.getenv('API_FRONT_URL')
origins = [
    api_front_url,
    f'{api_front_url}:8080',
    f'{api_front_url}:5173',
    f'{api_front_url}:3000'
]

app = FastAPI(title="CSV Analysis Agent API")

# Configuração CORS para permitir requests do React
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # porta do React
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/pergunta")
async def pergunta(pergunta: str = Form(...)):
    resposta = []
    try:
        resposta = agent.analyze_csv(pergunta)
        print("Resposta do agente:")
        print(resposta)
        saida_str = resposta.get("output", "").get("output", "")

        try:
            saida_json = json.loads(limpar_markdown_json(saida_str))
        except Exception:
            print("Resposta não é JSON válido")
            saida_json = None

        if eh_grafico(saida_json):
            return gerar_grafico_automatico(saida_json)
        else:
            # devolver resposta normal em texto
            return JSONResponse(content={"response": str(saida_json or saida_str)})
    except Exception as e:
        response_error = resposta.get("output", "")
        if response_error:
            return JSONResponse(content={"response": response_error})
        return JSONResponse(content={"response": f"Erro ao processar a pergunta: {str(e)}"})

def eh_grafico(resposta):
    print("Verificando se é gráfico:", resposta)
    """
    Verifica se a resposta contém dados reais para gráfico.
    """
    if isinstance(resposta, list) and all(isinstance(d, dict) for d in resposta):
        # Checa se existe chave 'distribution' com lista de bins ou valores
        for var in resposta:
            dist = var.get("distribution")
            if isinstance(dist, list) and len(dist) > 0 and all(isinstance(b, dict) for b in dist):
                return True
        # Caso seja lista de dicts (x/y)
        if isinstance(resposta, list) and all(isinstance(d, dict) for d in resposta):
            if all("x" in d and "y" in d for d in resposta):
                return True
        
        # Caso seja dict de colunas com min/max
        elif isinstance(resposta, dict):
            # Verifica se cada valor é um dict com 'min' e 'max'
            if all(isinstance(v, dict) and "min" in v and "max" in v for v in resposta.values()):
                return True
            if all(isinstance(v, dict) and "mínimo" in v and "máximo" in v for v in resposta.values()):
                return True
        
        df = pd.DataFrame(resposta)
        # Detecta colunas numéricas e categóricas
        cat_cols = df.select_dtypes(exclude="number").columns
        num_cols = df.select_dtypes(include="number").columns
        if len(cat_cols) > 0 and len(num_cols) > 0:
            return True
        else:
            print("Não há colunas categóricas e numéricas suficientes")
            return False
    elif isinstance(resposta, dict):
        if all(isinstance(v, dict) and "min" in v and "max" in v for v in resposta.values()):
            return True
        if all(isinstance(v, dict) and "mínimo" in v and "máximo" in v for v in resposta.values()):
            return True
        if all(isinstance(v, dict) and "mean" in v and "max" in v and "min" in v for v in resposta.values()):
            return True
        if all(isinstance(v, dict) and "média" in v and "máximo" in v and "mínimo" in v for v in resposta.values()):
            return True
        if all(isinstance(v, dict) and "variable" in v and "max" in v and "min" in v for v in resposta.values()):
            return True
    print("Resposta não é lista de dicts")
    return False

def limpar_markdown_json(resposta: str) -> str:
    """
    Remove blocos de código Markdown do tipo ```json ... ``` ou ``` ... ``` da string.
    Retorna apenas o conteúdo limpo que pode ser parseado como JSON.
    """
    if not isinstance(resposta, str):
        return resposta  # Não é string, retorna como está

    # Regex para remover qualquer bloco ```...```
    resposta_limpa = re.sub(r'```.*?```', '', resposta, flags=re.DOTALL)
    
    # Remove espaços em excesso e quebras de linha no início/fim
    resposta_limpa = resposta_limpa.strip()
    return resposta_limpa

def eh_grafico_old(resposta):
    """
    Verifica se a resposta é um formato válido para gráfico:
    - Lista de dicts
    - Contendo pelo menos uma coluna categórica e uma numérica
    """
    print("Verificando se é gráfico:", resposta)
    
    # Verifica se é lista de dicionários
    if isinstance(resposta, list) and all(isinstance(d, dict) for d in resposta):
        print("Resposta é lista de dicts")
        try:
            df = pd.DataFrame(resposta)
            # Detecta colunas numéricas e categóricas
            cat_cols = df.select_dtypes(exclude="number").columns
            num_cols = df.select_dtypes(include="number").columns
            if len(cat_cols) > 0 and len(num_cols) > 0:
                return True
            else:
                print("Não há colunas categóricas e numéricas suficientes")
                return False
        except Exception as e:
            print("Erro ao criar DataFrame:", e)
            return False
    
    print("Resposta não é lista de dicts")
    return False

def tipo_grafico(resposta):
    """
    Detecta se a resposta da LLM pode ser transformada em gráfico.
    Retorna o tipo de gráfico:
        - "xy" → lista de dicts com x/y
        - "categorical" → contagem de categorias
        - "stats" → estatísticas numéricas
        - None → não é gráfico
    """

    # 1️⃣ Lista de dicts com x/y
    if isinstance(resposta, list) and all(isinstance(d, dict) for d in resposta):
        # caso x/y
        if all("x" in d and "y" in d for d in resposta):
            return "xy"
        # caso estatísticas (min/max ou variável)
        if all("min" in d and "max" in d for d in resposta):
            return "stats"
        if all("variable" in d and "min" in d and "max" in d for d in resposta):
            return "stats"

    # 2️⃣ Distribuição categórica
    if isinstance(resposta, dict):
        for v in resposta.values():
            # contagens
            if isinstance(v, dict) and all(isinstance(count, int) for count in v.values()):
                return "categorical"
            # estatísticas numéricas
            if isinstance(v, dict) and ("min" in v and "max" in v and "mean" in v):
                return "stats"
            if isinstance(v, dict) and ("mínimo" in v and "máximo" in v and "média" in v):
                return "stats"

    print("Resposta não é válida para gráfico")
    return None

def gerar_grafico(resposta):
    print("Gerando gráfico com dados:")
    """
    Gera gráfico a partir da resposta da LLM.
    Retorna BytesIO pronto para StreamingResponse.
    """
    tipo = tipo_grafico(resposta)
    buf = BytesIO()
    print("Tipo de gráfico detectado:", tipo)
    if tipo == "xy":
        df = pd.DataFrame(resposta)
        plt.figure(figsize=(6,4))
        plt.plot(df["x"], df["y"], marker='o')
        plt.title("Gráfico gerado pela LLM")
        plt.xlabel("x")
        plt.ylabel("y")
        plt.grid(True)
        plt.tight_layout()
    
    elif tipo == "categorical":
        # pega a primeira chave categórica
        for k, v in resposta.items():
            if isinstance(v, dict) and all(isinstance(count, int) for count in v.values()):
                categorias = list(v.keys())
                counts = list(v.values())
                plt.figure(figsize=(6,4))
                plt.bar(categorias, counts)
                plt.title(f"Distribuição de {k}")
                plt.xlabel(k)
                plt.ylabel("Contagem")
                plt.xticks(rotation=45, ha="right")
                plt.grid(True)
                plt.tight_layout()
                break
    
    elif tipo == "stats":
        colunas = []
        valores = []
        label = ""

        if isinstance(resposta, dict):
            # Caso 1: resposta em formato dict com médias
            for col, stats in resposta.items():
                if isinstance(stats, dict) and "mean" in stats:
                    colunas.append(col)
                    valores.append(stats["mean"])
                    label = "Mean"
                elif isinstance(stats, dict) and "média" in stats:
                    colunas.append(col)
                    valores.append(stats["média"])
                    label = "Média"

        elif isinstance(resposta, list):
            # Caso 2: resposta em formato lista de dicts (min/max/variable)
            for item in resposta:
                if "variable" in item and "min" in item and "max" in item:
                    colunas.append(item["variable"])
                    # exemplo: diferença entre max e min (faixa)
                    valores.append(item["max"] - item["min"])
                    label = "Amplitude (max-min)"

        if colunas and valores:
            plt.figure(figsize=(10,5))
            plt.bar(colunas, valores)
            plt.xticks(rotation=90)
            plt.title("Estatísticas das variáveis")
            plt.ylabel(label)
            plt.grid(True)
            plt.tight_layout()
    
    else:
        raise ValueError("Resposta não é válida para gráfico")
    
    plt.savefig(buf, format="png")
    plt.close()
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Content-Disposition": "attachment; filename=grafico.png"}
    )


def gerar_grafico_automatico(dados):
    """
    Detecta automaticamente o tipo de dados e gera gráfico apropriado:
    - Lista de dicts com 'x'/'y' ou qualquer par categórica/numérica → barras
    - Lista de dicts com 'value'/'percentage' → pizza
    - Lista de variáveis com 'distribution' → histograma
    """
    print("Gerando gráfico automático com dados")

    if all(isinstance(v, dict) and "min" in v and "max" in v for v in dados):
        print("DEBUG: Detectado dados de min/max para gráfico de barras")

    if all(isinstance(v, dict) and "mínimo" in v and "máximo" in v for v in dados):
        print("DEBUG: Detectado dados de mínimo/máximo para gráfico de barras")

    # Caso seja histograma/distribution
    if isinstance(dados, list) and 'variable' in dados[0] and 'distribution' in dados[0]:
        print("Detectado dados de distribuição para histograma")

        for i in range(len(dados)):
            print(f"Processando variável {i+1}/{len(dados)}")
            var = dados[i]  # pegando a variável atual
            nome_var = var['variable']
            dist = var['distribution']

            # Detectar bins ou categorias
            if 'bin_range' in dist[0]:
                labels = [b['bin_range'] for b in dist]
            elif 'category' in dist[0]:
                labels = [b['category'] for b in dist]
            else:
                raise ValueError("Formato de distribuição desconhecido")

            counts = [b['count'] for b in dist]

            plt.figure(figsize=(10,6))
            plt.bar(labels, counts, color='skyblue')
            plt.xticks(rotation=45, ha='right')
            plt.title(f"Distribuição da variável {nome_var}")
            plt.xlabel(nome_var)
            plt.ylabel("Contagem")
            plt.grid(axis='y', linestyle='--', alpha=0.7)

    # Caso seja gráfico tipo pizza
    elif isinstance(dados, list) and 'value' in dados[0] and 'percentage' in dados[0]:
        print("Detectado dados para gráfico de pizza")
        df = pd.DataFrame(dados).sort_values('percentage', ascending=False).head(20)
        plt.figure(figsize=(8,8))
        plt.pie(df['percentage'], labels=df['value'], autopct="%1.1f%%", startangle=140)
        plt.title("Gráfico de Pizza")

    # Caso seja gráfico de barras genérico (x/y ou categórica/numérica)
    elif isinstance(dados, list) and all(isinstance(d, dict) for d in dados):
        print("Detectado dados para gráfico de barras")
        df = pd.DataFrame(dados)
        cat_cols = df.select_dtypes(exclude="number").columns
        num_cols = df.select_dtypes(include="number").columns
        if len(cat_cols) == 0 or len(num_cols) == 0:
            raise ValueError("Não foi possível identificar colunas para gráfico de barras.")
        cat_col = cat_cols[0]
        num_col = num_cols[0]
        df = df.sort_values(num_col, ascending=False).head(20)

        plt.figure(figsize=(10,6))
        plt.barh(df[cat_col], df[num_col], color="skyblue")
        plt.title("Gráfico de Barras")
        plt.xlabel(num_col)
        plt.ylabel(cat_col)
        plt.gca().invert_yaxis()
        plt.grid(axis="x", linestyle="--", alpha=0.7)
        print("dados para gráfico de barras ok")
    #{'Time': {'min': 0.0, 'max': 172792.0}, 'V1': {'min': -56.40751, 'max': 2.45493}, 'V2': {'min': -72.715728, 'max': 22.057729}, 'V3': {'min': -48.325589, 'max': 9.382558}, 'V4': {'min': -5.683171, 'max': 16.875344}, 'V5': {'min': -0.338321, 'max': 0.0600176}, 'V6': {'min': -0.0823608, 'max': 1.8005}, 'V7': {'min': -0.078803, 'max': 0.791461}, 'V8': {'min': 0.0851017, 'max': 0.377436}, 'V9': {'min': -0.255425, 'max': 0.363787}, 'V10': {'min': -0.166974, 'max': 0.207643}, 'V11': {'min': 1.61273, 'max': 1.61273}, 'V12': {'min': 0.0660837, 'max': 1.06524}, 'V13': {'min': -0.143772, 'max': 0.717293}, 'V14': {'min': -0.311169, 'max': 0.489095}, 'V15': {'min': 1.46818, 'max': 2.34586}, 'V16': {'min': -2.89008, 'max': 2.34586}, 'V17': {'min': -2.89008, 'max': 1.10997}, 'V18': {'min': -2.26186, 'max': 1.96578}, 'V19': {'min': -2.26186, 'max': 0.52498}, 'V20': {'min': -0.689281, 'max': 0.803487}, 'V21': {'min': -0.638672, 'max': 0.52498}, 'V22': {'min': -0.339846, 'max': 0.247998}, 'V23': {'min': -0.190321, 'max': 0.909412}, 'V24': {'min': -1.17558, 'max': 0.909412}, 'V25': {'min': 0.0052736, 'max': 0.798278}, 'V26': {'min': -0.190321, 'max': 0.141267}, 'V27': {'min': -1.17558, 'max': 0.502292}, 'V28': {'min': -0.221929, 'max': 0.219422}, 'Amount': {'min': 0.0, 'max': 25691.16}, 'Class': {'min': 0.0, 'max': 1.0}}
    elif isinstance(dados, dict) and all(isinstance(v, dict) and "min" in v and "max" in v for v in dados) or all(isinstance(v, dict) and "mínimo" in v and "máximo" in v for v in dados):
        print("dados para gráfico de min/max")
        df = pd.DataFrame(dados).T  # Transpor para ter colunas: min, max
        df.reset_index(inplace=True)
        df.rename(columns={'index': 'Variable'}, inplace=True)

        # Plot
        plt.figure(figsize=(10,6))
        plt.bar(df['Variable'], df['max'], label='Max', alpha=0.7)
        plt.bar(df['Variable'], df['min'], label='Min', alpha=0.7)
        plt.xticks(rotation=45, ha='right')
        plt.ylabel('Valores')
        plt.title('Min e Max das variáveis')
        plt.legend()
        plt.grid(axis='y') 
    else:
        print("Dados não reconhecidos para gráfico")
        raise ValueError("Formato de dados não suportado para gráfico.")

    # Salvar em PNG e retornar StreamingResponse
    buf = BytesIO()
    plt.tight_layout()
    plt.savefig(buf, format='png')
    plt.close()
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="image/png",
        headers={"Content-Disposition": "attachment; filename=grafico.png"}
    )

@app.get("/")
def root():
    return {"message": "API CSV Analysis Agent funcionando!"}

@app.get("/atual")
def current_file():
    if agent.current_file:
        return {"current_file": agent.current_file}
    return {"current_file": None, "message": "Nenhum arquivo carregado."}

@app.get("/health")
def read_health():
    return {"status": "OK"}

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    file_path = os.path.join("files", file.filename)
    print("Upload do arquivo")
    try:
        # Salvar arquivo
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        print("Carregar o arquivo")
        # Carregar CSV no agente
        if agent.carregar_arquivo(file_path):
            return {"message": f"Arquivo '{file.filename}' carregado com sucesso!", "filename": file.filename}
        else:
            return JSONResponse(status_code=400, content={"message": "Erro ao carregar o arquivo."})
    except Exception as e:
        return JSONResponse(status_code=400, content={"message": f"Erro: {str(e)}"})
