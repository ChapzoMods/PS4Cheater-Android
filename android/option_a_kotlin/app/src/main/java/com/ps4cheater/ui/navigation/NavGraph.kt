package com.ps4cheater.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.ps4cheater.data.Ps4Repository
import com.ps4cheater.data.PythonBridge
import com.ps4cheater.ui.screens.CheatTableScreen
import com.ps4cheater.ui.screens.ConnectScreen
import com.ps4cheater.ui.screens.HexEditorScreen
import com.ps4cheater.ui.screens.ProcessListScreen
import com.ps4cheater.ui.screens.ScannerScreen

/**
 * Type-safe navigation routes for PS4Cheater.
 *
 * Each [Screen] subclass exposes its `route` string used by the NavHost.
 */
sealed class Screen(val route: String) {
    object Connect : Screen("connect")
    object ProcessList : Screen("procs")
    object Scanner : Screen("scanner")
    object HexEditor : Screen("memory")
    object CheatTable : Screen("cheats")
}

/**
 * PS4CheaterNavHost — root navigation composable.
 *
 * Creates a single [Ps4Repository] backed by a [PythonBridge] instance,
 * kept alive with [remember] so it survives recompositions and is shared
 * by every screen in the graph.
 *
 * Routes:
 *  - [Screen.Connect]      (start destination) → [ConnectScreen]
 *  - [Screen.ProcessList]                      → [ProcessListScreen]
 *  - [Screen.Scanner]                          → [ScannerScreen]
 *  - [Screen.HexEditor]                        → [HexEditorScreen]
 *  - [Screen.CheatTable]                       → [CheatTableScreen]
 */
@Composable
fun PS4CheaterNavHost() {
    val navController: NavHostController = rememberNavController()
    val repository: Ps4Repository = remember { Ps4Repository(PythonBridge()) }

    NavHost(
        navController = navController,
        startDestination = Screen.Connect.route,
    ) {
        composable(Screen.Connect.route) {
            ConnectScreen(
                navController = navController,
                repository = repository,
            )
        }
        composable(Screen.ProcessList.route) {
            ProcessListScreen(
                navController = navController,
                repository = repository,
            )
        }
        composable(Screen.Scanner.route) {
            ScannerScreen(
                navController = navController,
                repository = repository,
            )
        }
        composable(Screen.HexEditor.route) {
            HexEditorScreen(
                navController = navController,
                repository = repository,
            )
        }
        composable(Screen.CheatTable.route) {
            CheatTableScreen(
                navController = navController,
                repository = repository,
            )
        }
    }
}
