// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "RafRaf",
    platforms: [
        .iOS(.v17),
    ],
    products: [
        .library(
            name: "RafRaf",
            targets: ["RafRaf"]
        ),
    ],
    dependencies: [
        .package(url: "https://github.com/hmlongco/Factory.git", from: "2.4.0"),
        .package(url: "https://github.com/kean/Nuke.git", from: "12.8.0"),
    ],
    targets: [
        .target(
            name: "RafRaf",
            dependencies: [
                "Factory",
                .product(name: "Nuke", package: "Nuke"),
                .product(name: "NukeUI", package: "Nuke"),
            ],
            path: "RafRaf"
        ),
        .testTarget(
            name: "RafRafTests",
            dependencies: ["RafRaf"],
            path: "RafRafTests"
        ),
    ]
)
