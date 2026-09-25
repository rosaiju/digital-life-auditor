import {
  View,
  Text,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  StyleSheet,
  RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useInsights, useGenerateInsights, hasInsights } from "@/hooks/useInsights";
import { showAlert, errorMessage } from "@/utils/alerts";
import { InsightCard } from "@/components/InsightCard";
import { EmptyState } from "@/components/EmptyState";
import { parseTimestamp } from "@/utils/dates";

export default function Insights() {
  const { data, isLoading, isRefetching, isError, error, refetch } = useInsights();
  const generate = useGenerateInsights();

  function handleGenerate() {
    generate.mutate(undefined, {
      onSuccess: () => refetch(),
      onError: (e) => showAlert("Couldn't generate insights", errorMessage(e)),
    });
  }

  if (isLoading) {
    return (
      <SafeAreaView style={styles.container}>
        <ActivityIndicator color="#6366f1" style={{ marginTop: 80 }} />
      </SafeAreaView>
    );
  }

  if (isError) {
    return (
      <SafeAreaView style={styles.container}>
        <EmptyState
          title="Couldn't load insights"
          subtitle={errorMessage(error)}
          actionLabel="Try again"
          onAction={() => refetch()}
        />
      </SafeAreaView>
    );
  }


  return (
    <SafeAreaView style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor="#6366f1" />
        }
      >
        <View style={styles.header}>
          <Text style={styles.title}>AI Insights</Text>
          <TouchableOpacity
            style={[styles.generateBtn, generate.isPending && styles.generateBtnDisabled]}
            onPress={handleGenerate}
            disabled={generate.isPending}
          >
            {generate.isPending ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.generateBtnText}>✦ Generate</Text>
            )}
          </TouchableOpacity>
        </View>

        {!hasInsights(data) ? (
          <EmptyState
            title="No insights yet"
            subtitle="Tap Generate to analyze your subscriptions"
            actionLabel="Generate Insights"
            onAction={handleGenerate}
          />
        ) : (
          <>
            {/* Summary */}
            <View style={styles.summaryCard}>
              <Text style={styles.summaryText}>{data.summary}</Text>
            </View>

            {/* Spend stats */}
            <View style={styles.statsRow}>
              <View style={styles.statBox}>
                <Text style={styles.statValue}>${data.monthly_total.toFixed(2)}</Text>
                <Text style={styles.statLabel}>Per Month</Text>
              </View>
              <View style={styles.statBox}>
                <Text style={styles.statValue}>${data.yearly_total.toFixed(2)}</Text>
                <Text style={styles.statLabel}>Per Year</Text>
              </View>
              <View style={styles.statBox}>
                <Text style={styles.statValue}>{data.subscription_count}</Text>
                <Text style={styles.statLabel}>Active</Text>
              </View>
            </View>

            {/* Top opportunity */}
            {data.top_opportunity && (
              <View style={styles.opportunityCard}>
                <Text style={styles.opportunityLabel}>Top Opportunity</Text>
                <Text style={styles.opportunityText}>{data.top_opportunity}</Text>
              </View>
            )}

            {/* Insight cards */}
            {data.insights.map((insight, i) => (
              <InsightCard key={i} insight={insight} />
            ))}

            {/* Category breakdown */}
            {Object.keys(data.category_breakdown).length > 0 && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>By Category</Text>
                {Object.entries(data.category_breakdown)
                  .sort(([, a], [, b]) => b - a)
                  .map(([cat, amount]) => (
                    <View key={cat} style={styles.categoryRow}>
                      <Text style={styles.categoryName}>{cat}</Text>
                      <Text style={styles.categoryAmount}>${amount.toFixed(2)}/mo</Text>
                    </View>
                  ))}
              </View>
            )}

            <Text style={styles.generatedAt}>
              Generated {parseTimestamp(data.generated_at).toLocaleDateString()}
              {data.source === "rules" ? " · rule-based analysis" : data.source === "ai" ? " · AI-written" : ""}
            </Text>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0f172a" },
  scroll: { paddingHorizontal: 16, paddingBottom: 40 },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingTop: 16,
    marginBottom: 16,
  },
  title: { fontSize: 24, fontWeight: "700", color: "#f8fafc" },
  generateBtn: {
    backgroundColor: "#6366f1",
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  generateBtnDisabled: { opacity: 0.6 },
  generateBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  summaryCard: {
    backgroundColor: "#1e293b",
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: "#334155",
  },
  summaryText: { color: "#cbd5e1", fontSize: 14, lineHeight: 22 },
  statsRow: { flexDirection: "row", gap: 10, marginBottom: 16 },
  statBox: {
    flex: 1,
    backgroundColor: "#1e293b",
    borderRadius: 12,
    padding: 14,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#334155",
  },
  statValue: { color: "#f8fafc", fontSize: 20, fontWeight: "700" },
  statLabel: { color: "#64748b", fontSize: 11, marginTop: 2 },
  opportunityCard: {
    backgroundColor: "#312e81",
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: "#4338ca",
  },
  opportunityLabel: { color: "#a5b4fc", fontSize: 11, fontWeight: "600", marginBottom: 6 },
  opportunityText: { color: "#e0e7ff", fontSize: 14, lineHeight: 20 },
  section: {
    backgroundColor: "#1e293b",
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: "#334155",
  },
  sectionTitle: { color: "#94a3b8", fontSize: 12, fontWeight: "600", marginBottom: 12 },
  categoryRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "#0f172a",
  },
  categoryName: { color: "#cbd5e1", fontSize: 14 },
  categoryAmount: { color: "#94a3b8", fontSize: 14 },
  generatedAt: { color: "#334155", fontSize: 11, textAlign: "center", marginTop: 8 },
});
