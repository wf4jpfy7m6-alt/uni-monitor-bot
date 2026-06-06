import aiohttp
import asyncio
import logging
from web3 import Web3

# Ваш существующий код (ABI и константы) остается без изменений, 
# просто вставьте его сюда для полноты файла.

class PositionMonitor:
    def __init__(self, wallet_address: str):
        self.wallet = Web3.to_checksum_address(wallet_address)
        self.web3_clients = {
            network: Web3(Web3.HTTPProvider(rpc))
            for network, rpc in RPC_URLS.items()
        }

    async def get_all_positions(self) -> list:
        positions = []
        # Сначала Base (Aerodrome)
        base_pos = await self._get_positions_on_network("Base", self.web3_clients["Base"])
        positions.extend(base_pos)
        
        # Затем Arbitrum (через Subgraph)
        arb_pos = await self._get_arbitrum_positions_subgraph()
        positions.extend(arb_pos)
        
        return positions

    async def _get_arbitrum_positions_subgraph(self) -> list:
        query = """
        {
          positions(where: {owner: "%s"}) {
            id
            liquidity
            tickLower
            tickUpper
            pool { token0 { symbol } token1 { symbol } }
          }
        }
        """ % self.wallet.lower()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(SUBGRAPHS["Arbitrum"], json={'query': query}) as resp:
                    result = await resp.json()
                    data = result.get("data", {}).get("positions", [])
                    return [{"token_id": int(p['id']), "network": "Arbitrum", "pair": f"{p['pool']['token0']['symbol']}/{p['pool']['token1']['symbol']}"} for p in data if int(p['liquidity']) > 0]
        except Exception as e:
            logging.error(f"Ошибка Subgraph Arbitrum: {e}")
            return []

    # ... (далее ваш оригинальный метод _get_positions_on_network для Base)
