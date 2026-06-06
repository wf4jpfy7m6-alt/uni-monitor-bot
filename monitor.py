import aiohttp
import asyncio
import logging
from web3 import Web3

logger = logging.getLogger(__name__)

SUBGRAPHS = {
    "Arbitrum": "https://api.thegraph.com/subgraphs/name/ianlapham/arbitrum-minimal",
    "Base": "https://api.studio.thegraph.com/query/48211/uniswap-v3-base/version/latest",
}
RPC_URLS = {"Arbitrum": "https://arb1.arbitrum.io/rpc", "Base": "https://mainnet.base.org"}
POSITION_MANAGER_ADDRESSES = {"Arbitrum": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88", "Base": "0x827922686190790b37229fd06084350E74485b72"}
FACTORY_ADDRESSES = {"Arbitrum": "0x1F98431c8aD98523631AE4a59f267346ea31F984", "Base": "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"}

POSITION_MANAGER_ABI = [{"inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}], "name": "positions", "outputs": [{"internalType": "uint96", "name": "nonce", "type": "uint96"}, {"internalType": "address", "name": "operator", "type": "address"}, {"internalType": "address", "name": "token0", "type": "address"}, {"internalType": "address", "name": "token1", "type": "address"}, {"internalType": "uint24", "name": "fee", "type": "uint24"}, {"internalType": "int24", "name": "tickLower", "type": "int24"}, {"internalType": "int24", "name": "tickUpper", "type": "int24"}, {"internalType": "uint128", "name": "liquidity", "type": "uint128"}, {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"}, {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"}, {"internalType": "uint128", "name": "tokensOwed0", "type": "uint128"}, {"internalType": "uint128", "name": "tokensOwed1", "type": "uint128"}], "stateMutability": "view", "type": "function"}, {"inputs": [{"internalType": "address", "name": "owner", "type": "address"}], "name": "balanceOf", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"}, {"inputs": [{"internalType": "address", "name": "owner", "type": "address"}, {"internalType": "uint256", "name": "index", "type": "uint256"}], "name": "tokenOfOwnerByIndex", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"}]
ERC20_ABI = [{"inputs": [], "name": "symbol", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"}, {"inputs": [], "name": "decimals", "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}], "stateMutability": "view", "type": "function"}]
POOL_ABI = [{"inputs": [], "name": "slot0", "outputs": [{"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"}, {"internalType": "int24", "name": "tick", "type": "int24"}, {"internalType": "uint16", "name": "observationIndex", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"}, {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"}, {"internalType": "bool", "name": "unlocked", "type": "bool"}], "stateMutability": "view", "type": "function"}, {"inputs": [], "name": "token0", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"}, {"inputs": [], "name": "token1", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"}]
FACTORY_ABI = [{"inputs": [{"internalType": "address", "name": "tokenA", "type": "address"}, {"internalType": "address", "name": "tokenB", "type": "address"}, {"internalType": "uint24", "name": "fee", "type": "uint24"}], "name": "getPool", "outputs": [{"internalType": "address", "name": "pool", "type": "address"}], "stateMutability": "view", "type": "function"}]

class PositionMonitor:
    def __init__(self, wallet_address: str):
        self.wallet = Web3.to_checksum_address(wallet_address)
        self.web3_clients = {network: Web3(Web3.HTTPProvider(rpc)) for network, rpc in RPC_URLS.items()}

    async def get_all_positions(self) -> list:
        # Мониторинг обеих сетей
        positions = await self._get_positions_on_network("Base", self.web3_clients["Base"])
        positions.extend(await self._get_arbitrum_positions_subgraph())
        return positions

    async def _get_arbitrum_positions_subgraph(self) -> list:
        query = """{ positions(where: {owner: "%s"}) { id liquidity pool { token0 { symbol } token1 { symbol } } } }""" % self.wallet.lower()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(SUBGRAPHS["Arbitrum"], json={'query': query}) as resp:
                    result = await resp.json()
                    data = result.get("data", {}).get("positions", [])
                    return [{"token_id": int(p['id']), "network": "Arbitrum", "pair": f"{p['pool']['token0']['symbol']}/{p['pool']['token1']['symbol']}", "liquidity": int(p['liquidity'])} for p in data if int(p['liquidity']) > 0]
        except Exception as e:
            logger.error(f"Ошибка Subgraph Arbitrum: {e}")
            return []

    async def _get_positions_on_network(self, network: str, w3: Web3) -> list:
        loop = asyncio.get_event_loop()
        try:
            pm_address = POSITION_MANAGER_ADDRESSES.get(network, POSITION_MANAGER_ADDRESSES["Arbitrum"])
            pm = w3.eth.contract(address=Web3.to_checksum_address(pm_address), abi=POSITION_MANAGER_ABI)
            balance = await loop.run_in_executor(None, pm.functions.balanceOf(self.wallet).call)
            if balance == 0: return []
            positions = []
            for i in range(balance):
                token_id = await loop.run_in_executor(None, pm.functions.tokenOfOwnerByIndex(self.wallet, i).call)
                # Упрощенная логика для сбора базовых данных
                positions.append({"token_id": token_id, "network": network})
            return positions
        except Exception as e:
            logger.error(f"Ошибка на {network}: {e}")
            return []
