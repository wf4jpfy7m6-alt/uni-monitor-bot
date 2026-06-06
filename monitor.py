import asyncio
import logging
from web3 import Web3

logger = logging.getLogger(__name__)

RPC_URLS = {
    "Arbitrum": "https://arb1.arbitrum.io/rpc",
}

POSITION_MANAGER_ADDRESSES = {
    "Arbitrum": "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
}

POSITION_MANAGER_ABI = [
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "positions",
        "outputs": [
            {"internalType": "uint96",  "name": "nonce",                    "type": "uint96"},
            {"internalType": "address", "name": "operator",                 "type": "address"},
            {"internalType": "address", "name": "token0",                   "type": "address"},
            {"internalType": "address", "name": "token1",                   "type": "address"},
            {"internalType": "uint24",  "name": "fee",                      "type": "uint24"},
            {"internalType": "int24",   "name": "tickLower",                "type": "int24"},
            {"internalType": "int24",   "name": "tickUpper",                "type": "int24"},
            {"internalType": "uint128", "name": "liquidity",                "type": "uint128"},
            {"internalType": "uint256", "name": "feeGrowthInside0LastX128", "type": "uint256"},
            {"internalType": "uint256", "name": "feeGrowthInside1LastX128", "type": "uint256"},
            {"internalType": "uint128", "name": "tokensOwed0",              "type": "uint128"},
            {"internalType": "uint128", "name": "tokensOwed1",              "type": "uint128"}
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "uint256", "name": "index", "type": "uint256"}
        ],
        "name": "tokenOfOwnerByIndex",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

ERC20_ABI = [
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function"
    }
]

POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96",              "type": "uint160"},
            {"internalType": "int24",   "name": "tick",                      "type": "int24"},
            {"internalType": "uint16",  "name": "observationIndex",          "type": "uint16"},
            {"internalType": "uint16",  "name": "observationCardinality",    "type": "uint16"},
            {"internalType": "uint16",  "name": "observationCardinalityNext","type": "uint16"},
            {"internalType": "uint8",   "name": "feeProtocol",               "type": "uint8"},
            {"internalType": "bool",    "name": "unlocked",                  "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

FACTORY_ADDRESS = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
FACTORY_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "tokenA", "type": "address"},
            {"internalType": "address", "name": "tokenB", "type": "address"},
            {"internalType": "uint24",  "name": "fee",    "type": "uint24"}
        ],
        "name": "getPool",
        "outputs": [{"internalType": "address", "name": "pool", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

import math

def tick_to_price(tick, decimals0=18, decimals1=6):
    try:
        raw = 1.0001 ** tick
        return float(raw * (10 ** (decimals0 - decimals1)))
    except Exception:
        return 0.0

def liquidity_to_amounts(liquidity, sqrt_price_x96, tick_lower, tick_upper, decimals0=18, decimals1=6):
    try:
        if liquidity == 0:
            return 0.0, 0.0
        Q96 = 2 ** 96
        sp = sqrt_price_x96 / Q96
        sl = math.sqrt(1.0001 ** tick_lower)
        su = math.sqrt(1.0001 ** tick_upper)
        if sp <= sl:
            a0 = liquidity * (1/sl - 1/su)
            a1 = 0.0
        elif sp >= su:
            a0 = 0.0
            a1 = liquidity * (su - sl)
        else:
            a0 = liquidity * (1/sp - 1/su)
            a1 = liquidity * (sp - sl)
        return float(a0 / 10**decimals0), float(a1 / 10**decimals1)
    except Exception as e:
        logger.error(f"liquidity_to_amounts error: {e}")
        return 0.0, 0.0


class PositionMonitor:
    def __init__(self, wallet_address: str):
        self.wallet = Web3.to_checksum_address(wallet_address)
        self.w3 = Web3(Web3.HTTPProvider(RPC_URLS["Arbitrum"]))
        self.pm = self.w3.eth.contract(
            address=Web3.to_checksum_address(POSITION_MANAGER_ADDRESSES["Arbitrum"]),
            abi=POSITION_MANAGER_ABI
        )
        self.factory = self.w3.eth.contract(
            address=Web3.to_checksum_address(FACTORY_ADDRESS),
            abi=FACTORY_ABI
        )

    async def get_all_positions(self) -> list:
        return await asyncio.to_thread(self._get_positions_sync)

    def _get_token_info(self, address):
        try:
            c = self.w3.eth.contract(address=Web3.to_checksum_address(address), abi=ERC20_ABI)
            symbol = c.functions.symbol().call()
            decimals = c.functions.decimals().call()
            return symbol, decimals
        except Exception:
            return "???", 18

    def _get_positions_sync(self) -> list:
        try:
            balance = self.pm.functions.balanceOf(self.wallet).call()
        except Exception as e:
            logger.error(f"Arbitrum balanceOf error: {e}")
            return []

        results = []
        for i in range(balance):
            try:
                token_id = self.pm.functions.tokenOfOwnerByIndex(self.wallet, i).call()
                pos = self.pm.functions.positions(token_id).call()

                token0_addr = pos[2]
                token1_addr = pos[3]
                fee         = pos[4]
                tick_lower  = pos[5]
                tick_upper  = pos[6]
                liquidity   = pos[7]

                if liquidity == 0:
                    continue

                sym0, dec0 = self._get_token_info(token0_addr)
                sym1, dec1 = self._get_token_info(token1_addr)

                # Получаем текущую цену из пула
                current_price = 0.0
                sqrt_price_x96 = 0
                try:
                    pool_addr = self.factory.functions.getPool(token0_addr, token1_addr, fee).call()
                    if pool_addr != "0x0000000000000000000000000000000000000000":
                        pool = self.w3.eth.contract(address=pool_addr, abi=POOL_ABI)
                        slot0 = pool.functions.slot0().call()
                        sqrt_price_x96 = int(slot0[0])
                        current_price = tick_to_price(int(slot0[1]), dec0, dec1)
                except Exception as e:
                    logger.warning(f"Arbitrum pool price error: {e}")

                price_lower = tick_to_price(tick_lower, dec0, dec1)
                price_upper = tick_to_price(tick_upper, dec0, dec1)
                if price_lower > price_upper:
                    price_lower, price_upper = price_upper, price_lower

                in_range = price_lower <= current_price <= price_upper if current_price else False

                amount0, amount1 = liquidity_to_amounts(
                    liquidity, sqrt_price_x96, tick_lower, tick_upper, dec0, dec1
                )

                # Оценка стоимости в USD (грубо — через price)
                if current_price and current_price > 0:
                    value_usd = amount0 * current_price + amount1
                else:
                    value_usd = 0.0

                results.append({
                    "network":       "Arbitrum",
                    "token_id":      token_id,
                    "token0":        sym0,
                    "token1":        sym1,
                    "price_lower":   round(price_lower, 2),
                    "price_upper":   round(price_upper, 2),
                    "current_price": round(current_price, 2),
                    "in_range":      in_range,
                    "value_usd":     value_usd,
                })
            except Exception as e:
                logger.error(f"Arbitrum position error #{i}: {e}")

        return results
