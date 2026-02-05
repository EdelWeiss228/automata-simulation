import pandas as pd
import os
import glob

base_dir = "batch_analysis"
output_file = os.path.join(base_dir, "summary_stats.csv")

summary_path = os.path.join(base_dir, "summary_stats.csv")
summary_df = pd.read_csv(summary_path)

corrected_totals = []
rarely_counts = []
sometimes_counts = []
frequently_counts = []

freq_files = sorted(glob.glob(os.path.join(base_dir, "frequency_summary_*.csv")),
                    key=lambda x: int(os.path.splitext(os.path.basename(x))[0].split("_")[-1]))

for freq_file in freq_files:
    df = pd.read_csv(freq_file)
    total = df["pair_count"].sum()
    corrected_totals.append(total)

    df_sorted = df.set_index("frequency_class").reindex(["Rarely", "Sometimes", "Frequently"])
    rarely_counts.append(df_sorted.loc["Rarely", "pair_count"])
    sometimes_counts.append(df_sorted.loc["Sometimes", "pair_count"])
    frequently_counts.append(df_sorted.loc["Frequently", "pair_count"])


summary_df.loc[:len(corrected_totals)-1, "total_pairs"] = corrected_totals
summary_df.loc[:len(rarely_counts)-1, "Rarely_count"] = rarely_counts
summary_df.loc[:len(sometimes_counts)-1, "Sometimes_count"] = sometimes_counts
summary_df.loc[:len(frequently_counts)-1, "Frequently_count"] = frequently_counts

mean_rarely = pd.Series(rarely_counts).dropna().mean()
mean_sometimes = pd.Series(sometimes_counts).dropna().mean()
mean_frequently = pd.Series(frequently_counts).dropna().mean()
mean_total_pairs = pd.Series(corrected_totals).dropna().mean()





summary_df.to_csv(output_file, index=False)
print(f"Updated enhanced summary saved to: {output_file}")
