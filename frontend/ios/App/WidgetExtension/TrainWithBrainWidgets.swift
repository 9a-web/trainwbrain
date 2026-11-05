//
//  TrainWithBrainWidgets.swift
//  WidgetExtension
//
//  Live Activity widget for Dynamic Island and Lock Screen.
//  Displays current workout progress: exercise name, sets, weights, and timer.
//

import WidgetKit
import SwiftUI

@available(iOS 16.1, *)
struct TWBWidgetExtension: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: TWBAttributes.self) { context in
            // ---- Lock Screen / Banner ----
            TWBLiveActivityView(context: context)
        } dynamicIsland: { context in
            // ---- Dynamic Island ----
            DynamicIsland {
                // Expanded view (pressed and held)
                DynamicIslandExpandedRegion(.leading) {
                    TWBDIIconView()
                }
                DynamicIslandExpandedRegion(.trailing) {
                    TWBDISetsView(context: context)
                }
                DynamicIslandExpandedRegion(.center) {
                    TWBIDExerciseNameView(context: context)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    TWBDIProgressBar(context: context)
                }
            } compactLeading: {
                // Compact leading (left side)
                TWBDIIconView()
            } compactTrailing: {
                // Compact trailing (right side)
                Text("\(context.state.setsCompleted)/\(context.state.totalSets)")
                    .font(.system(.caption, design: .rounded).monospacedDigit())
                    .foregroundColor(.orange)
            } minimal: {
                // Minimal (when another app takes the leading spot)
                Image(systemName: "dumbbell.fill")
                    .foregroundColor(.orange)
            }
        }
        .supplementalActivityFamilies([.small, .medium])
    }
}

// MARK: - Lock Screen / Banner View

@available(iOS 16.1, *)
private struct TWBLiveActivityView: View {
    let context: ActivityViewContext<TWBAttributes>

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "dumbbell.fill")
                .font(.title2)
                .foregroundColor(.orange)

            VStack(alignment: .leading, spacing: 2) {
                Text(context.state.exerciseName)
                    .font(.headline)
                    .lineLimit(1)

                HStack(spacing: 8) {
                    if !context.state.weight.isEmpty {
                        Label(context.state.weight, systemImage: "scalemass")
                            .font(.caption)
                    }
                    if !context.state.repScheme.isEmpty {
                        Text(context.state.repScheme)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                ProgressView(
                    value: Double(context.state.setsCompleted),
                    total: Double(max(context.state.totalSets, 1))
                )
                .tint(.orange)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text("\(context.state.setsCompleted)/\(context.state.totalSets)")
                    .font(.title3.monospacedDigit())
                    .fontWeight(.bold)
                    .foregroundColor(.orange)

                if context.state.elapsedMinutes > 0 {
                    Text(timeFormatted(minutes: context.state.elapsedMinutes))
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }
        }
        .padding()
        .activityBackgroundTint(Color.black.opacity(0.85))
        .activitySystemActionForegroundColor(.white)
    }

    private func timeFormatted(minutes: Int) -> String {
        let h = minutes / 60
        let m = minutes % 60
        return h > 0 ? "\(h)ч \(m)м" : "\(m)м"
    }
}

// MARK: - Dynamic Island Views

@available(iOS 16.1, *)
private struct TWBDIIconView: View {
    var body: some View {
        Image(systemName: "dumbbell.fill")
            .font(.system(.caption))
            .foregroundColor(.orange)
    }
}

@available(iOS 16.1, *)
private struct TWBDISetsView: View {
    let context: ActivityViewContext<TWBAttributes>

    var body: some View {
        Text("\(context.state.setsCompleted)/\(context.state.totalSets)")
            .font(.system(.caption, design: .rounded).monospacedDigit())
            .foregroundColor(.orange)
    }
}

@available(iOS 16.1, *)
private struct TWBIDExerciseNameView: View {
    let context: ActivityViewContext<TWBAttributes>

    var body: some View {
        Text(context.state.exerciseName)
            .font(.caption)
            .lineLimit(1)
    }
}

@available(iOS 16.1, *)
private struct TWBDIProgressBar: View {
    let context: ActivityViewContext<TWBAttributes>

    var body: some View {
        HStack(spacing: 8) {
            if !context.state.weight.isEmpty {
                Label(context.state.weight, systemImage: "scalemass")
                    .font(.caption2)
            }

            ProgressView(
                value: Double(context.state.setsCompleted),
                total: Double(max(context.state.totalSets, 1))
            )
            .tint(.orange)
            .frame(maxWidth: 120)
        }
    }
}