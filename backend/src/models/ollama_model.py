import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Carrega variáveis do arquivo .env
load_dotenv()

# Model configuration com timeout
ollama_model = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "minimax-m2.7:cloud"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0.0,
    streaming=False
)

# Configuração de retry com tenacity
def create_retry_decorator():
    return retry(
        stop=stop_after_attempt(int(os.getenv("OLLAMA_MAX_RETRIES", "3"))),
        wait=wait_exponential(multiplier=10, min=10, max=120),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        reraise=True,
    )

# Wrapper com retry para uso em agentes
class OllamaModelWithRetry:
    def __init__(self, model, retry_decorator):
        self.model = model
        self.retry_decorator = retry_decorator

    @property
    def ainvoke(self):
        return self._with_retry(self.model.ainvoke)

    @property
    def invoke(self):
        return self._with_retry(self.model.invoke)

    def _with_retry(self, method):
        return self.retry_decorator(method)

# Criar modelo com retry
ollama_model_with_retry = OllamaModelWithRetry(ollama_model, create_retry_decorator())