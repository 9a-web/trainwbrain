//
//  WidgetExtension.swift
//  WidgetExtension
//
//  The main entry point for the widget extension bundle.
//

import SwiftUI
import WidgetKit

@main
struct TWBWidgetsBundle: WidgetBundle {
    var body: some Widget {
        if #available(iOS 16.1, *) {
            TWBWidgetExtension()
        }
    }
}