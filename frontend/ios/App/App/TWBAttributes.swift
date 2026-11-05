import Foundation
import ActivityKit

/// ActivityAttributes for the TrainWithBrain workout Live Activity.
/// These attributes are static (set at activity creation time).
public struct TWBAttributes: ActivityAttributes {

    /// Unique session identifier used to match WebSocket updates.
    public let sessionId: String

    public init(sessionId: String) {
        self.sessionId = sessionId
    }

    /// Dynamic content state updated via push or local updates.
    public struct ContentState: Codable, Hashable {
        /// Name of the current exercise (e.g. "Жим лёжа").
        public var exerciseName: String
        /// Number of completed sets for the current exercise.
        public var setsCompleted: Int
        /// Total sets planned for the current exercise.
        public var totalSets: Int
        /// Rep scheme description (e.g. "5x5" or "10/8/6").
        public var repScheme: String
        /// Weight with unit (e.g. "80 кг").
        public var weight: String
        /// Status string: "active", "rest", "finished"
        public var status: String
        /// Elapsed training time in minutes (for compact display).
        public var elapsedMinutes: Int
    }
}

/// Type alias for convenience.
public typealias TWBContentState = TWBAttributes.ContentState