from finance import fetch_prices, basic_stats, plot_prices

data = fetch_prices()
for ticker, df in data.items():
    print(f"\nTicker: {ticker}")
    stats = basic_stats(df)
    for k, v in stats.items():
        print(f"  {k}: {v:.2f}")

    # grafica
    plot_prices(df, ticker)
