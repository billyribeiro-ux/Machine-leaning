import { isReady } from './scanify-core';

export function computeSMA(data: number[], period: number): number[] {
	if (isReady()) {
		// Would call WASM implementation
	}
	const result: number[] = [];
	for (let i = 0; i < data.length; i++) {
		if (i < period - 1) {
			result.push(NaN);
			continue;
		}
		let sum = 0;
		for (let j = i - period + 1; j <= i; j++) {
			sum += data[j]!;
		}
		result.push(sum / period);
	}
	return result;
}

export function computeEMA(data: number[], period: number): number[] {
	if (isReady()) {
		// Would call WASM implementation
	}
	const result: number[] = [];
	const multiplier = 2 / (period + 1);
	let ema = data[0]!;
	result.push(ema);
	for (let i = 1; i < data.length; i++) {
		ema = (data[i]! - ema) * multiplier + ema;
		result.push(ema);
	}
	return result;
}

export function computeRSI(data: number[], period: number = 14): number[] {
	if (isReady()) {
		// Would call WASM implementation
	}
	const result: number[] = [NaN];
	const gains: number[] = [];
	const losses: number[] = [];

	for (let i = 1; i < data.length; i++) {
		const change = data[i]! - data[i - 1]!;
		gains.push(change > 0 ? change : 0);
		losses.push(change < 0 ? -change : 0);

		if (i < period) {
			result.push(NaN);
			continue;
		}

		let avgGain: number;
		let avgLoss: number;

		if (i === period) {
			avgGain = gains.reduce((s, g) => s + g, 0) / period;
			avgLoss = losses.reduce((s, l) => s + l, 0) / period;
		} else {
			const prevRsi = result[result.length - 1];
			if (isNaN(prevRsi!)) {
				avgGain = gains.slice(-period).reduce((s, g) => s + g, 0) / period;
				avgLoss = losses.slice(-period).reduce((s, l) => s + l, 0) / period;
			} else {
				avgGain = (gains.slice(-period - 1, -1).reduce((s, g) => s + g, 0) / period * (period - 1) + gains[gains.length - 1]!) / period;
				avgLoss = (losses.slice(-period - 1, -1).reduce((s, l) => s + l, 0) / period * (period - 1) + losses[losses.length - 1]!) / period;
			}
		}

		if (avgLoss === 0) {
			result.push(100);
		} else {
			const rs = avgGain / avgLoss;
			result.push(100 - 100 / (1 + rs));
		}
	}
	return result;
}

export function computeMACD(
	data: number[],
	fastPeriod: number = 12,
	slowPeriod: number = 26,
	signalPeriod: number = 9
): { macd: number[]; signal: number[]; histogram: number[] } {
	const fastEma = computeEMA(data, fastPeriod);
	const slowEma = computeEMA(data, slowPeriod);
	const macdLine = fastEma.map((f, i) => f - slowEma[i]!);
	const signalLine = computeEMA(macdLine, signalPeriod);
	const histogram = macdLine.map((m, i) => m - signalLine[i]!);
	return { macd: macdLine, signal: signalLine, histogram };
}

export function computeBollingerBands(
	data: number[],
	period: number = 20,
	stdDevMultiplier: number = 2
): { upper: number[]; middle: number[]; lower: number[] } {
	const middle = computeSMA(data, period);
	const upper: number[] = [];
	const lower: number[] = [];

	for (let i = 0; i < data.length; i++) {
		if (i < period - 1) {
			upper.push(NaN);
			lower.push(NaN);
			continue;
		}
		const slice = data.slice(i - period + 1, i + 1);
		const mean = middle[i]!;
		const variance = slice.reduce((sum, val) => sum + (val - mean) ** 2, 0) / period;
		const stdDev = Math.sqrt(variance);
		upper.push(mean + stdDevMultiplier * stdDev);
		lower.push(mean - stdDevMultiplier * stdDev);
	}
	return { upper, middle, lower };
}

export function computeVWAP(prices: number[], volumes: number[]): number[] {
	const result: number[] = [];
	let cumulativeTPV = 0;
	let cumulativeVolume = 0;

	for (let i = 0; i < prices.length; i++) {
		cumulativeTPV += prices[i]! * volumes[i]!;
		cumulativeVolume += volumes[i]!;
		result.push(cumulativeVolume > 0 ? cumulativeTPV / cumulativeVolume : prices[i]!);
	}
	return result;
}
