import asyncio
import logging
from web3 import Web3

logger = logging.getLogger(__name__)

BASE_RPC = "https://mainnet.base.org"

# Aerodrome Sugar v3 — читает все позиции включая застейканные
SUGAR_ADDRESS = "0xa7638d351040e2adce3eca81b07132c5df4b99bd"
CL_FACTORY = "0x5e7BB104d84c7CB9B682AaC2F3d509f5F406809A"

SUGAR_ABI = [
    {
        "name": "positionsByFactory",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "_limit", "type": "uint256"},
            {"name": "_offset", "type": "uint256"},
            {"name": "_account", "type": "address"},
            {"name": "_factory", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "tuple[]", "components": [
            {"name": "id", "type": "uint256"},
            {"name": "lp", "type": "address"},
            {"name": "liquidity", "type": "uint256"},
            {"name": "staked", "type": "uint256"},
            {"name": "amount0", "type": "uint256"},
            {"name": "amount1", "type": "uint256"},
            {"name": "staked0", "type": "uint256"},
            {"name": "staked1", "type": "uint256"},
            {"name": "unstaked_earned0", "type": "uint256"},
            {"name": "unstaked_earned1", "type": "uint256"},
            {"name": "emissions_earned", "type": "uint256"},
            {"name": "tick_lower", "type": "int24"},
            {"name": "tick_upper", "type": "int24"},
            {"name": "sqrt_ratio_lower", "type": "uint160"},
            {"name": "sqrt_ratio_upper", "type": "uint160"},
        ]}],
    }
]

POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "", "type": "uint16"},
            {"internalType": "uint16", "name": "", "type": "uint16"},
            {"internalType": "uint16", "name": "", "type": "uint16"},
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

ERC20_ABI = [
    {"inputs": [], "name": "symbol", "outputs": [{"type": "string"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "decimals", "outputs": [{"type": "uint8"}], "stateMutability": "view", "type": "function"},
]

STABLECOINS = {"USDC", "USDT", "DAI", "USDbC", "USDBC", "USDC.e"}


class AerodromeMonitor:
    def __init__(self, wallet_address: str):
        self.wallet = Web3.to_checksum_address(wallet_address)
        self.w3 = Web3(Web3.HTTPProvider(BASE_RPC))

    async def get_positions(self) -> list:
        loop = asyncio.get_event_loop()
        try:
            sugar = self.w3.eth.contract(
                address=Web3.to_checksum_address(SUGAR_ADDRESS),
                abi=SUGAR_ABI
            )
            logger.info(f"Aerodrome: вызываю Sugar.positionsByFactory для {self.wallet}")
            raw = await loop.run_in_executor(
                None,
                sugar.functions.positionsByFactory(
                    100, 0, self.wallet,
                    Web3.to_checksum_address(CL_FACTORY)
                ).call
            )
            logger.info(f"Aerodrome: Sugar вернул {len(raw)} позиций")

            positions = []
            for p in raw:
                try:
                    pos = await self._parse(p, loop)
                    if pos:
                        positions.append(pos)
                except Exception as e:
                    logger.error(f"Aerodrome parse error: {e}")

            return positions

        except Exception as e:
            logger.error(f"Aerodrome Sugar error: {e}")
            return []

    async def _parse(self, p, loop) -> dict:
        liquidity = p[2] + p[3]  # liquidity + staked
        if liquidity == 0:
            return None

        pool_addr = p[1]
        tick_lower = p[11]
        tick_upper = p[12]

        pool = self.w3.eth.contract(address=Web3.to_checksum_address(pool_addr), abi=POOL_ABI)

        token0_addr = await loop.run_in_executor(None, pool.functions.token0().call)
        token1_addr = await loop.run_in_executor(None, pool.functions.token1().call)
        slot0 = await loop.run_in_executor(None, pool.functions.slot0().call)
        current_tick = slot0[1]
        sqrt_price_x96 = slot0[0]

        t0 = self.w3.eth.contract(address=token0_addr, abi=ERC20_ABI)
        t1 = self.w3.eth.contract(address=token1_addr, abi=ERC20_ABI)
        symbol0 = await loop.run_in_executor(None, t0.functions.symbol().call)
        symbol1 = await loop.run_in_executor(None, t1.functions.symbol().call)
        decimals0 = await loop.run_in_executor(None, t0.functions.decimals().call)
        decimals1 = await loop.run_in_executor(None, t1.functions.decimals().call)

        def tick_to_price(tick):
            price = 1.0001 ** tick
            return price * (10 ** decimals0) / (10 ** decimals1)

        current_price_raw = (sqrt_price_x96 / (2 ** 96)) ** 2 * (10 ** decimals0) / (10 ** decimals1)
        price_lower = tick_to_price(tick_lower)
        price_upper = tick_to_price(tick_upper)

        # Определяем читаемое отображение цены
        if symbol1 in STABLECOINS:
            display_price = current_price_raw
            display_lower = price_lower
            display_upper = price_upper
        elif symbol0 in STABLECOINS:
            display_price = 1 / current_price_raw if current_price_raw > 0 else 0
            display_lower = 1 / price_upper if price_upper > 0 else 0
            display_upper = 1 / price_lower if price_lower > 0 else 0
        else:
            display_price = current_price_raw
            display_lower = price_lower
            display_upper = price_upper

        in_range = tick_lower <= current_tick <= tick_upper

        # Стоимость через amount0 + amount1 из Sugar (уже с учётом стейкинга)
        total0 = (p[4] + p[6]) / (10 ** decimals0)  # amount0 + staked0
        total1 = (p[5] + p[7]) / (10 ** decimals1)  # amount1 + staked1

        if symbol1 in STABLECOINS:
            value_usd = total0 * display_price + total1
        elif symbol0 in STABLECOINS:
            value_usd = total0 + total1 * display_price
        else:
            value_usd = total0 * display_price + total1

        return {
            "token_id": p[0],
            "network": "Base (Aerodrome)",
            "token0": symbol0,
            "token1": symbol1,
            "fee": 0.05,
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
