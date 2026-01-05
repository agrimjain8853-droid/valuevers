import numpy as np


def remove_outliers_iqr(prices):
    """
    Removes outliers using the IQR method.
    """
    prices = np.array(prices)

    q1 = np.percentile(prices, 25)
    q3 = np.percentile(prices, 75)
    iqr = q3 - q1

    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    return prices[(prices >= lower_bound) & (prices <= upper_bound)]


def trimmed_mean(prices, trim_ratio=0.1):
    """
    Calculates trimmed mean by removing top & bottom trim_ratio.
    """
    prices = np.sort(prices)
    n = len(prices)

    trim_count = int(n * trim_ratio)

    if n <= 2 * trim_count:
        return float(np.mean(prices))

    trimmed_prices = prices[trim_count : n - trim_count]
    return float(np.mean(trimmed_prices))


def confidence_score(original_prices, used_points):
    """
    Returns LOW / MEDIUM / HIGH confidence based on data quality.
    """
    total_points = len(original_prices)
    outlier_ratio = 1 - (used_points / total_points)

    std_dev = np.std(original_prices)
    mean_price = np.mean(original_prices)

    volatility = std_dev / mean_price if mean_price else 0

    if used_points >= 10 and volatility < 0.15 and outlier_ratio < 0.2:
        return "HIGH"
    elif used_points >= 5 and volatility < 0.25:
        return "MEDIUM"
    else:
        return "LOW"


def fair_value(prices):
    """
    Main fair value calculation.
    """
    if len(prices) < 3:
        raise ValueError("Not enough data points")

    original_prices = prices.copy()

    cleaned_prices = remove_outliers_iqr(prices)

    if len(cleaned_prices) == 0:
        raise ValueError("All data points considered outliers")

    median_price = float(np.median(cleaned_prices))
    trimmed_avg = trimmed_mean(cleaned_prices)

    # Weighted blend: robust + responsive
    fair_price = 0.6 * median_price + 0.4 * trimmed_avg

    result = {
        "fair_value": round(fair_price, 2),
        "median": round(median_price, 2),
        "trimmed_mean": round(trimmed_avg, 2),
        "data_points_used": int(len(cleaned_prices)),
    }

    # ✅ Add confidence
    result["confidence"] = confidence_score(
        original_prices,
        result["data_points_used"]
    )

    return result


if __name__ == "__main__":
    sample_prices = [
        48000, 50000, 52000, 51000, 49500,
        49000, 70000, 30000, 50500, 49800
    ]

    print(fair_value(sample_prices))
