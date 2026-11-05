// swift-tools-version: 5.7
import PackageDescription

let package = Package(
    name: "TrainWithBrain",
    platforms: [
        .iOS(.v16)
    ],
    products: [
        .library(
            name: "TrainWithBrain",
            targets: ["App", "WidgetExtension"]
        ),
    ],
    dependencies: [],
    targets: [
        .target(
            name: "App",
            dependencies: [],
            path: "App"
        ),
        .target(
            name: "WidgetExtension",
            dependencies: [],
            path: "WidgetExtension"
        ),
    ]
)