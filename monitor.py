import aiohttp
import asyncio
import logging
from web3 import Web3

logger = logging.getLogger(__name__)

# --- ВАШИ КОНСТАНТЫ (ОСТАВЛЯЕМ КАК БЫЛО) ---
SUBGRAPHS = {
    "Arbitrum": "https://api.thegraph.com/subgraphs/name/ianlapham/arbitrum-minimal",
    "Base": "https://api.studio.thegraph.com/query/48211/uniswap-v3-base/version/latest",
}
RPC_URLS = {"Arbitrum": "https://arb1.arbitrum.io/rpc", "Base": "https://mainnet.base.org"}
POSITION_MANAGER_ADDRESSES = {"Arbitrum": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88", "Base": "0x827922686190790b37229fd06084350E74485b72"}
FACTORY_ADDRESSES = {"Arbitrum": "0x1F98431c8aD98523631AE4a59f267346ea31F984", "Base": "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"}
# ... (здесь должны быть ваши ABI: POSITION_MANAGER_ABI, ERC20_ABI, POOL_ABI, FACTORY_ABI) ...

class PositionMonitor:
    def __init__(self, wallet_address: str):
        self.wallet = Web3.to_checksum_address(wallet_address)
        self.web3_clients = {network: Web3(Web3.HTTPProvider(rpc)) for network, rpc in RPC_URLS.items()}

    async def get_all_positions(self) -> list:
        """Собираем позиции из всех источников."""
        # 1. Base (через RPC)
        base_pos = await self._get_positions_on_network("Base", self.web3_clients["Base"])
        # 2. Arbitrum (через Subgraph)
        arb_pos = await self._get_arbitrum_positions_subgraph()
        return base_pos + arb_pos

    async def _get_arbitrum_positions_subgraph(self) -> list:
        """Быстрый мониторинг Uniswap через Subgraph."""
        query = """{ positions(where: {owner: "%s"}) { id liquidity pool { token0 { symbol } token1 { symbol } } } }""" % self.wallet.lower()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(SUBGRAPHS["Arbitrum"], json={'query': query}) as resp:
                    result = await resp.json()
                    data = result.get("data", {}).get("positions", [])
                    return [{"token_id": int(p['id']), "network": "Arbitrum", "pair": f"{p['pool']['token0']['symbol']}/{p['pool']['token1']['symbol']}"} for p in data if int(p['liquidity']) > 0]
        except Exception as e:
            logger.error(f"Ошибка Subgraph Arbitrum: {e}")
            return []

    async def _get_positions_on_network(self, network: str, w3: Web3) -> list:
        """Ваша оригинальная логика для Base (Aerodrome)."""
        # Сюда вставьте ваш оригинальный код метода _get_positions_on_network,
        # который был у вас до этого. 
        # (Весь блок кода, начинающийся с try: ... и заканчивающийся return [])
        pass
