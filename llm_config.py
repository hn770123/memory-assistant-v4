# === 設定ファイルベースの切り替え ===
import os
from typing import Literal

class LLMConfig:
    """環境変数や設定ファイルからプロバイダーを選択"""
    
    @staticmethod
    def from_env() -> UniversalExtractor:
        provider = os.getenv("LLM_PROVIDER", "anthropic")
        
        configs = {
            "anthropic": {
                "provider": LLMProvider.ANTHROPIC,
                "client_kwargs": {"api_key": os.getenv("ANTHROPIC_API_KEY")}
            },
            "ollama": {
                "provider": LLMProvider.OLLAMA,
                "client_kwargs": {"base_url": os.getenv("OLLAMA_URL", "http://localhost:11434")}
            },
            "cloudflare": {
                "provider": LLMProvider.CLOUDFLARE,
                "client_kwargs": {
                    "account_id": os.getenv("CF_ACCOUNT_ID"),
                    "api_token": os.getenv("CF_API_TOKEN")
                }
            }
        }
        
        config = configs.get(provider)
        if not config:
            raise ValueError(f"未対応のプロバイダー: {provider}")
        
        return UniversalExtractor(**config)


# === 使い方（アプリケーションコード） ===
# .env ファイル:
# LLM_PROVIDER=ollama
# OLLAMA_URL=http://localhost:11434

# アプリケーション側は環境に依存しない
extractor = LLMConfig.from_env()
result, info = extractor.extract(text, AnalysisResult)


# === フォールバックチェーン ===
class MultiProviderExtractor:
    """複数プロバイダーでフォールバック"""
    
    def __init__(self):
        self.extractors = [
            UniversalExtractor(LLMProvider.OLLAMA),      # まずローカル
            UniversalExtractor(LLMProvider.CLOUDFLARE),  # 次にエッジ
            UniversalExtractor(LLMProvider.ANTHROPIC),   # 最後にクラウド
        ]
    
    def extract(self, text: str, response_model: Type[T]) -> tuple[T, dict]:
        """プロバイダー間でもフォールバック"""
        for extractor in self.extractors:
            try:
                return extractor.extract(
                    text,
                    response_model,
                    enable_escalation=False  # プロバイダー内はエスカレーションなし
                )
            except Exception as e:
                print(f"⚠️ {extractor.provider.value} 失敗、次を試行...")
                continue
        
        raise Exception("全プロバイダーで失敗")


# === コスト最適化 ===
class CostOptimizedExtractor(UniversalExtractor):
    """コストを意識した抽出"""
    
    def extract_cheap(self, text: str, response_model: Type[T]) -> tuple[T, dict]:
        """最も安いモデルのみ使用（エスカレーションなし）"""
        return self.extract(
            text,
            response_model,
            start_tier=1,
            enable_escalation=False
        )
    
    def extract_smart(self, text: str, response_model: Type[T]) -> tuple[T, dict]:
        """適応的にモデルを選択"""
        # テキストの複雑度を推定
        complexity = len(text) / 1000 + len(text.split()) / 100
        
        if complexity < 2:
            start_tier = 1
        elif complexity < 5:
            start_tier = 2
        else:
            start_tier = 3
        
        return self.extract(text, response_model, start_tier=start_tier)
