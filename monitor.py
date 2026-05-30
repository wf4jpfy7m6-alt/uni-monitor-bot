import aiohttp
import asyncio
import math
import logging
from web3 import Web3

logger = logging.getLogger(__name__)

# Uniswap v3 subgraph endpoints
SUBGRAPHS = {
    "Arbitrum": "https://api.thegraph.com/subgraphs/name/ianlapham/arbitrum-minimal",
    "Base": "https://api.studio.thegraph.com/query/48211/uniswap-v3-base/version/latest",
}

# Fallback: прямое чтение через RPC
RPC_URLS = {
    "Arbitrum": "https://arb1.arbitrum.io/rpc",
    "Base": "https://mainnet.base.org",
}

POSITION_MANAGER_ADDRESS = "0xC36442b4a4522E871399CD717aBDD847Ab11FE88"  # одинаковый на всех сетях

POSITION_MANAGER_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "positions",
        "outputs": [
            {"internalType": "uint96", "name": "nonce", "type": "uint96"},
            {"internalType": "address", "name": "operator", "type": "address"},
            {"internalType": "address", "name": "token0", "type": "address"},
            {"internalType": "address", "name": "token1", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
            {"internalType": "int24", "name": "tickLower", "type": "int24"},
            {"internalType": "int24", "name": "tickUpper", "type": "int24"},
            {"internalType": "uint128", "name": "liquidity", "type": "uint128"},
            {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
            {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
            {"internalType": "uint128", "name": "tokensOwed0", "type": "uint128"},
            {"internalType": "uint128", "name": "tokensOwed1", "type": "uint128"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "uint256", "name": "index", "type": "uint256"},
        ],
        "name": "tokenOfOwnerByIndex",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

ERC20_ABI = [
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24", "name": "fee", "type": "uint24"},
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    }
]

FACTORY_ADDRESS = "0x1F98431c8aD98523631AE4a59f267346ea31F984"

# Известные стейблкоины для определения цены
STABLECOINS = {
    "USDC", "USDT", "DAI", "USDC.e", "USDBC"
}

# Известные wrapped tokens
WRAPPED_NATIVES = {
    "WETH": "ETH",
    "WBTC": "BTC",
}


def tick_to_price(tick: int, decimals0: int, decimals1: int) -> float:
    """Конвертация tick в цену с учётом decimals."""
    price = 1.0001 ** tick
    price = price * (10 ** decimals0) / (10 ** decimals1)
    return price


def sqrt_price_x96_to_price(sqrt_price_x96: int, decimals0: int, decimals1: int) -> float:
    """Конвертация sqrtPriceX96 в читаемую цену."""
    price = (sqrt_price_x96 / (2 ** 96)) ** 2
    price = price * (10 ** decimals0) / (10 ** decimals1)
    return price


class PositionMonitor:
    def __init__(self, wallet_address: str):
        self.wallet = Web3.to_checksum_address(wallet_address)
        self.web3_clients = {
            network: Web3(Web3.HTTPProvider(rpc))
            for network, rpc in RPC_URLS.items()
        }

    async def get_all_positions(self) -> list:
        """Получить все активные позиции на всех сетях."""
        tasks = [
            self._get_positions_on_network(network, w3)
            for network, w3 in self.web3_clients.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        positions = []
        for r in results:
            if isinstance(r, list):
                positions.extend(r)
            elif isinstance(r, Exception):
                logger.error(f"Ошибка получения позиций: {r}")
        return positions

    async def _get_positions_on_network(self, network: str, w3: Web3) -> list:
        """Получить позиции на конкретной сети через RPC."""
        loop = asyncio.get_event_loop()
        try:
            pm = w3.eth.contract(
                address=Web3.to_checksum_address(POSITION_MANAGER_ADDRESS),
                abi=POSITION_MANAGER_ABI
            )

            # Получаем количество NFT позиций
            balance = await loop.run_in_executor(
                None, pm.functions.balanceOf(self.wallet).call
            )

            if balance == 0:
                return []

            positions = []
            for i in range(balance):
                try:
                    token_id = await loop.run_in_executor(
                        None, pm.functions.tokenOfOwnerByIndex(self.wallet, i).call
                    )
                    pos = await self._parse_position(w3, pm, token_id, network, loop)
                    if pos and pos["liquidity"] > 0:
                        positions.append(pos)
                except Exception as e:
                    logger.error(f"Ошибка позиции {i} на {network}: {e}")

            return positions

        except Exception as e:
            logger.error(f"Ошибка на {network}: {e}")
            return []

    async def _parse_position(self, w3, pm, token_id: int, network: str, loop) -> dict:
        """Парсит одну позицию и возвращает все данные."""
        pos_data = await loop.run_in_executor(
            None, pm.functions.positions(token_id).call
        )

        liquidity = pos_data[7]
        if liquidity == 0:
            return None

        token0_addr = pos_data[2]
        token1_addr = pos_data[3]
        fee = pos_data[4]
        tick_lower = pos_data[5]
        tick_upper = pos_data[6]

        # Получаем символы и decimals токенов
        t0 = w3.eth.contract(address=token0_addr, abi=ERC20_ABI)
        t1 = w3.eth.contract(address=token1_addr, abi=ERC20_ABI)

        symbol0 = await loop.run_in_executor(None, t0.functions.symbol().call)
        symbol1 = await loop.run_in_executor(None, t1.functions.symbol().call)
        decimals0 = await loop.run_in_executor(None, t0.functions.decimals().call)
        decimals1 = await loop.run_in_executor(None, t1.functions.decimals().call)

        # Получаем текущую цену из пула
        factory = w3.eth.contract(
            address=Web3.to_checksum_address(FACTORY_ADDRESS),
            abi=FACTORY_ABI
        )
        pool_addr = await loop.run_in_executor(
            None,
            factory.functions.getPool(token0_addr, token1_addr, fee).call
        )

        pool = w3.eth.contract(address=pool_addr, abi=POOL_ABI)
        slot0 = await loop.run_in_executor(None, pool.functions.slot0().call)
        sqrt_price_x96 = slot0[0]
        current_tick = slot0[1]

        # Цены
        current_price = sqrt_price_x96_to_price(sqrt_price_x96, decimals0, decimals1)
        price_lower = tick_to_price(tick_lower, decimals0, decimals1)
        price_upper = tick_to_price(tick_upper, decimals0, decimals1)

        # Если token1 — стейблкоин, инвертируем для читаемости
        if symbol1 in STABLECOINS:
            display_price = current_price
            display_lower = price_lower
            display_upper = price_upper
            pair_display = f"{symbol0}/{symbol1}"
        elif symbol0 in STABLECOINS:
            display_price = 1 / current_price if current_price > 0 else 0
            display_lower = 1 / price_upper if price_upper > 0 else 0
            display_upper = 1 / price_lower if price_lower > 0 else 0
            pair_display = f"{symbol1}/{symbol0}"
        else:
            display_price = current_price
            display_lower = price_lower
            display_upper = price_upper
            pair_display = f"{symbol0}/{symbol1}"

        in_range = tick_lower <= current_tick <= tick_upper

        # Примерная стоимость (упрощённо)
        value_usd = self._estimate_value(liquidity, display_price, display_lower, display_upper)

        return {
            "token_id": token_id,
            "network": network,
            "token0": symbol0,
            "token1": symbol1,
            "pair_display": pair_display,
            "fee": fee / 10000,  # в процентах
            "tick_lower": tick_lower,
            "tick_upper": tick_upper,
            "current_tick": current_tick,
            "liquidity": liquidity,
            "current_price": display_price,
            "price_lower": display_lower,
            "price_upper": display_upper,
            "in_range": in_range,
            "value_usd": value_usd,
            "pool_address": pool_addr,
        }

    def _estimate_value(self, liquidity: int, price: float, lower: float, upper: float) -> float:
        """Грубая оценка стоимости позиции в USD."""
        if price <= 0 or lower <= 0 or upper <= 0:
            return 0
        try:
            sqrt_p = math.sqrt(price)
            sqrt_lower = math.sqrt(lower)
            sqrt_upper = math.sqrt(upper)

            if price <= lower:
                amount0 = liquidity * (1 / sqrt_lower - 1 / sqrt_upper) / 1e18
                return amount0 * price
            elif price >= upper:
                amount1 = liquidity * (sqrt_upper - sqrt_lower) / 1e18
                return amount1
            else:
                amount0 = liquidity * (1 / sqrt_p - 1 / sqrt_upper) / 1e18
                amount1 = liquidity * (sqrt_p - sqrt_lower) / 1e18
                return amount0 * price + amount1
        except Exception:
            return 0
