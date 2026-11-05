import Foundation
import Capacitor
import ActivityKit

/// Capacitor plugin for managing Dynamic Island / Live Activities
/// Corresponds to the `LiveActivityBridge` JavaScript API.
@objc(LiveActivityPlugin)
public class LiveActivityPlugin: CAPPlugin {

    // Currently active activity (only one at a time is supported for workout tracking)
    private var currentActivity: Activity<TWBAttributes>? = nil

    // MARK: - Start

    /// Start a Live Activity for a training session.
    /// - Call: `LiveActivityBridge.start({ sessionId, exerciseName, setsCompleted, totalSets, repScheme, weight, status })
    @objc func start(_ call: CAPPluginCall) {
        guard let sessionId = call.getString("sessionId") else {
            call.reject("Missing required parameter: sessionId")
            return
        }

        // Guard: iOS 16.1+ required for ActivityKit
        guard #available(iOS 16.1, *) else {
            call.reject("Live Activities require iOS 16.1 or later")
            return
        }

        // Guard: device must have an activity entitlement
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            call.reject("Live Activities are not enabled for this app. Enable in Settings > TrainWithBrain.")
            return
        }

        let exerciseName = call.getString("exerciseName") ?? "Тренировка"
        let setsCompleted = call.getInt("setsCompleted") ?? 0
        let totalSets = call.getInt("totalSets") ?? 0
        let repScheme = call.getString("repScheme") ?? ""
        let weight = call.getString("weight") ?? ""
        let status = call.getString("status") ?? "active"

        let attributes = TWBAttributes(sessionId: sessionId)

        let initialContentState = TWBContentState(
            exerciseName: exerciseName,
            setsCompleted: setsCompleted,
            totalSets: totalSets,
            repScheme: repScheme,
            weight: weight,
            status: status,
            elapsedMinutes: 0
        )

        do {
            let activity = try Activity.request(
                attributes: attributes,
                content: .init(state: initialContentState, staleDate: nil),
                pushType: nil
            )
            currentActivity = activity
            call.resolve(["activityId": activity.id])
        } catch {
            call.reject("Failed to start Live Activity: \(error.localizedDescription)")
        }
    }

    // MARK: - Update

    /// Update the currently displayed Live Activity with new data.
    /// - Call: `LiveActivityBridge.update({ exerciseName, setsCompleted, totalSets, repScheme, weight, status, elapsedMinutes })
    @objc func update(_ call: CAPPluginCall) {
        guard #available(iOS 16.1, *) else {
            call.reject("Live Activities require iOS 16.1 or later")
            return
        }

        guard let activity = currentActivity else {
            call.reject("No active Live Activity to update. Call start() first.")
            return
        }

        let exerciseName = call.getString("exerciseName") ?? activity.content.state.exerciseName
        let setsCompleted = call.getInt("setsCompleted") ?? activity.content.state.setsCompleted
        let totalSets = call.getInt("totalSets") ?? activity.content.state.totalSets
        let repScheme = call.getString("repScheme") ?? activity.content.state.repScheme
        let weight = call.getString("weight") ?? activity.content.state.weight
        let status = call.getString("status") ?? activity.content.state.status
        let elapsedMinutes = call.getInt("elapsedMinutes") ?? activity.content.state.elapsedMinutes

        let updatedState = TWBContentState(
            exerciseName: exerciseName,
            setsCompleted: setsCompleted,
            totalSets: totalSets,
            repScheme: repScheme,
            weight: weight,
            status: status,
            elapsedMinutes: elapsedMinutes
        )

        Task {
            await activity.update(
                ActivityContent<TWBContentState>(
                    state: updatedState,
                    staleDate: Date.now + 60 * 5 // stale after 5 minutes
                )
            )
            call.resolve(["updated": true])
        }
    }

    // MARK: - End

    /// End (dismiss) the current Live Activity.
    /// - Call: `LiveActivityBridge.end({ dismissalPolicy: "immediate" | "after" })
    @objc func end(_ call: CAPPluginCall) {
        guard #available(iOS 16.1, *) else {
            call.reject("Live Activities require iOS 16.1 or later")
            return
        }

        guard let activity = currentActivity else {
            call.reject("No active Live Activity to end.")
            return
        }

        let policyString = call.getString("dismissalPolicy") ?? "after"
        let policy: ActivityUIDismissalPolicy

        switch policyString {
        case "immediate":
            policy = .immediate
        case "after":
            // Default: dismiss after a short delay so the user sees the final state
            policy = .after(Date.now + 4.0)
        default:
            policy = .default
        }

        Task {
            await activity.end(activity.content, dismissalPolicy: policy)
            currentActivity = nil
            call.resolve(["ended": true])
        }
    }

    // MARK: - Check availability

    /// Check whether Live Activities are supported and enabled on this device.
    /// - Call: `LiveActivityBridge.isAvailable()`
    @objc func isAvailable(_ call: CAPPluginCall) {
        guard #available(iOS 16.1, *) else {
            call.resolve(["available": false, "reason": "unsupported_os"])
            return
        }
        call.resolve([
            "available": ActivityAuthorizationInfo().areActivitiesEnabled,
            "supportsDynamicIsland": UIDevice.current.userInterfaceIdiom == .phone
        ])
    }

    // MARK: - Get active activity ID

    /// Return the id of the currently running Live Activity, if any.
    @objc func getActiveActivityId(_ call: CAPPluginCall) {
        guard #available(iOS 16.1, *) else {
            call.resolve(["activityId": nil])
            return
        }
        call.resolve(["activityId": currentActivity?.id as Any])
    }
}