package top.hypixice.poros.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.VideocamOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Slider
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import top.hypixice.poros.BuildConfig
import top.hypixice.poros.MicPhase
import top.hypixice.poros.MicState
import top.hypixice.poros.R
import top.hypixice.poros.data.HostProfile
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.IconButton

@Composable
fun MicScreen(viewModel: MicViewModel, onLanguageChanged: () -> Unit = {}) {
    val context = LocalContext.current
    val state by viewModel.state.collectAsStateWithLifecycle()
    val micLevel = viewModel.level.collectAsStateWithLifecycle()
    val cameraOn by viewModel.cameraOn.collectAsStateWithLifecycle()
    var errorText by remember { mutableStateOf<String?>(null) }
    var addHostOpen by remember { mutableStateOf(false) }
    var editProfile by remember { mutableStateOf<HostProfile?>(null) }
    var settingsOpen by remember { mutableStateOf(false) }

    val runtimePermissions = remember {
        buildList {
            add(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }.toTypedArray()
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { result ->
        if (result[Manifest.permission.RECORD_AUDIO] == true) {
            errorText = null
            viewModel.connect()
        } else {
            errorText = context.getString(R.string.error_mic_permission)
        }
    }

    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            errorText = null
            viewModel.toggleCamera()
        } else {
            errorText = context.getString(R.string.camera_error_permission)
        }
    }

    fun startSession() {
        val micGranted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
        if (micGranted) {
            errorText = null
            viewModel.connect()
        } else {
            permissionLauncher.launch(runtimePermissions)
        }
    }

    fun toggleCamera() {
        val granted = ContextCompat.checkSelfPermission(
            context, Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
        when {
            cameraOn -> {
                errorText = null
                viewModel.toggleCamera()
            }
            granted -> {
                errorText = null
                viewModel.toggleCamera()
            }
            else -> cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    val active = state.phase == MicPhase.STREAMING || state.phase == MicPhase.CONNECTING

    Box(Modifier.fillMaxSize()) {
    Scaffold(containerColor = MaterialTheme.colorScheme.background) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 20.dp, vertical = 12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Filled.Mic,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary
                )
                Spacer(Modifier.size(8.dp))
                Text(
                    text = stringResource(R.string.app_name),
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onBackground
                )
                Spacer(Modifier.size(6.dp))
                Text(
                    text = BuildConfig.VERSION_NAME,
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.weight(1f))
                IconButton(onClick = { settingsOpen = true }) {
                    Icon(
                        imageVector = Icons.Filled.Menu,
                        contentDescription = stringResource(R.string.settings_title),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            Spacer(Modifier.height(24.dp))

            StatusCard(state)

            Spacer(Modifier.height(12.dp))

            if (viewModel.profiles.isEmpty()) {
                OutlinedButton(
                    onClick = { addHostOpen = true },
                    enabled = !active,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Icon(
                        imageVector = Icons.Filled.Add,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(Modifier.size(6.dp))
                    Text(stringResource(R.string.host_add))
                }
            } else {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    LazyRow(
                        modifier = Modifier.weight(1f),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        userScrollEnabled = !active
                    ) {
                        items(viewModel.profiles, key = { it.address }) { profile ->
                            HostChip(
                                profile = profile,
                                selected = profile.address == viewModel.address.trim(),
                                onClick = { viewModel.selectProfile(profile) },
                                onLongClick = { editProfile = profile }
                            )
                        }
                    }
                    Spacer(Modifier.size(4.dp))
                    IconButton(onClick = { addHostOpen = true }, enabled = !active) {
                        Icon(
                            imageVector = Icons.Filled.Add,
                            contentDescription = stringResource(R.string.host_add),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }

            Spacer(Modifier.height(12.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.Top
            ) {
                OutlinedTextField(
                    value = viewModel.address,
                    onValueChange = viewModel::onAddressChange,
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                    enabled = !active,
                    label = { Text(stringResource(R.string.address_label)) },
                    placeholder = { Text(stringResource(R.string.address_hint)) }
                )
                Spacer(Modifier.width(8.dp))
                OutlinedTextField(
                    value = viewModel.pin,
                    onValueChange = viewModel::onPinChange,
                    modifier = Modifier.width(118.dp),
                    singleLine = true,
                    enabled = !active,
                    label = { Text(stringResource(R.string.pin_label)) }
                )
            }

            Spacer(Modifier.height(16.dp))

            Column(Modifier.fillMaxWidth()) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = stringResource(R.string.gain),
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = stringResource(R.string.gain_value, viewModel.gain),
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Slider(
                    value = viewModel.gain,
                    onValueChange = viewModel::onGainChange,
                    valueRange = 0f..3f
                )
            }

            // The mic pad absorbs whatever vertical space is left, so the page
            // fits one screen instead of scrolling to reach Connect. The button
            // stays thumb-sized; the level halo around it is the real feedback.
            BoxWithConstraints(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                contentAlignment = Alignment.Center
            ) {
                val canvasSize = (minOf(maxWidth.value / 2f - 12f, maxHeight.value))
                    .coerceAtMost(150f).dp
                Row(
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    MicPad(
                        levelState = micLevel,
                        micState = state,
                        active = active,
                        canvasSize = canvasSize,
                        onToggle = { viewModel.toggleMute() },
                    )
                    // The camera streams straight from the service - there is no
                    // preview here, this button is the whole camera UI.
                    CameraPad(
                        canvasSize = canvasSize,
                        enabled = active,
                        on = cameraOn,
                        onToggle = { toggleCamera() },
                    )
                }
            }

            (errorText ?: state.error)?.let { message ->
                Text(
                    text = message,
                    color = MaterialTheme.colorScheme.error,
                    fontSize = 13.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }

            Spacer(Modifier.height(8.dp))

            Button(
                onClick = { if (active) viewModel.disconnect() else startSession() },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                colors = if (active) {
                    ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant,
                        contentColor = MaterialTheme.colorScheme.onSurface
                    )
                } else {
                    ButtonDefaults.buttonColors()
                }
            ) {
                Icon(
                    imageVector = if (active) Icons.Filled.Stop else Icons.Filled.PlayArrow,
                    contentDescription = null
                )
                Spacer(Modifier.size(8.dp))
                Text(
                    text = stringResource(if (active) R.string.disconnect else R.string.connect),
                    fontSize = 16.sp
                )
            }

            Spacer(Modifier.height(8.dp))
        }
    }

    SettingsDrawer(
        open = settingsOpen,
        language = viewModel.language,
        version = BuildConfig.VERSION_NAME,
        onLanguageSelected = { code ->
            viewModel.selectLanguage(code)
            onLanguageChanged()
        },
        onClose = { settingsOpen = false },
    )
    }

    if (addHostOpen) {
        HostDialog(
            title = stringResource(R.string.host_add_title),
            confirmLabel = stringResource(R.string.host_add),
            initialAddress = viewModel.address.trim(),
            onDismiss = { addHostOpen = false },
            onConfirm = { name, address, description ->
                viewModel.addProfile(name, address, description)
                addHostOpen = false
            }
        )
    }

    // Long-pressing a host opens the same form, pre-filled, with delete offered
    // at the bottom for when that is what was wanted.
    editProfile?.let { profile ->
        HostDialog(
            title = stringResource(R.string.host_edit_title),
            confirmLabel = stringResource(R.string.host_save),
            initialName = profile.name,
            initialAddress = profile.address,
            initialDescription = profile.description,
            onDismiss = { editProfile = null },
            onConfirm = { name, address, description ->
                viewModel.updateProfile(profile, name, address, description)
                editProfile = null
            },
            onDelete = {
                viewModel.deleteProfile(profile)
                editProfile = null
            }
        )
    }
}

@Composable
private fun MicPad(
    levelState: State<Float>,
    micState: MicState,
    active: Boolean,
    canvasSize: Dp,
    onToggle: () -> Unit,
) {
    val buttonSize = 64.dp
    val (buttonColor, icon, tint) = micAppearance(micState)
    val rawLevel = if (active) levelState.value else 0f
    // WebRTC's audioLevel is a small linear value for normal speech, so scale it
    // up hard or the halo barely moves.
    val target = (rawLevel * 4f).coerceIn(0f, 1f)
    val display by animateFloatAsState(
        targetValue = target,
        animationSpec = tween(durationMillis = 90),
        label = "micLevel",
    )

    Box(Modifier.size(canvasSize), contentAlignment = Alignment.Center) {
        Canvas(Modifier.fillMaxSize()) {
            val baseRadius = buttonSize.toPx() / 2f
            val scale = 1f + display * 1.4f
            val alpha = (0.15f + display * 0.45f).coerceAtMost(0.6f)
            drawCircle(color = buttonColor.copy(alpha = alpha), radius = baseRadius * scale)
        }
        Surface(
            onClick = onToggle,
            enabled = active,
            shape = CircleShape,
            color = buttonColor,
            modifier = Modifier.size(buttonSize)
        ) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = tint,
                    modifier = Modifier.size(30.dp)
                )
            }
        }
    }
}

@Composable
private fun CameraPad(
    canvasSize: Dp,
    enabled: Boolean,
    on: Boolean,
    onToggle: () -> Unit,
) {
    val buttonSize = 64.dp
    val live = on && enabled
    val buttonColor = if (live) {
        MaterialTheme.colorScheme.primary
    } else {
        MaterialTheme.colorScheme.surfaceVariant
    }
    val tint = if (live) {
        MaterialTheme.colorScheme.onPrimary
    } else {
        MaterialTheme.colorScheme.onSurfaceVariant
    }

    Box(Modifier.size(canvasSize), contentAlignment = Alignment.Center) {
        Surface(
            onClick = onToggle,
            enabled = enabled,
            shape = CircleShape,
            color = buttonColor,
            modifier = Modifier.size(buttonSize)
        ) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Icon(
                    imageVector = if (on) Icons.Filled.Videocam else Icons.Filled.VideocamOff,
                    contentDescription = null,
                    tint = tint,
                    modifier = Modifier.size(30.dp)
                )
            }
        }
    }
}

@Composable
private fun BoxScope.SettingsDrawer(
    open: Boolean,
    language: String,
    version: String,
    onLanguageSelected: (String) -> Unit,
    onClose: () -> Unit,
) {
    AnimatedVisibility(visible = open, enter = fadeIn(), exit = fadeOut()) {
        Box(
            Modifier
                .fillMaxSize()
                .background(Color.Black.copy(alpha = 0.5f))
                .clickable { onClose() }
        )
    }
    AnimatedVisibility(
        visible = open,
        enter = slideInHorizontally(initialOffsetX = { it }),
        exit = slideOutHorizontally(targetOffsetX = { it }),
        modifier = Modifier.align(Alignment.CenterEnd),
    ) {
        SettingsPanel(language, version, onLanguageSelected, onClose)
    }
}

@Composable
private fun SettingsPanel(
    language: String,
    version: String,
    onLanguageSelected: (String) -> Unit,
    onClose: () -> Unit,
) {
    Surface(
        modifier = Modifier
            .width(300.dp)
            .fillMaxHeight(),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 4.dp,
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(20.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = stringResource(R.string.settings_title),
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Medium,
                    color = MaterialTheme.colorScheme.onSurface,
                )
                IconButton(onClick = onClose) {
                    Icon(
                        imageVector = Icons.Filled.Close,
                        contentDescription = stringResource(R.string.settings_close),
                        tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            Spacer(Modifier.height(20.dp))
            Text(
                text = stringResource(R.string.settings_language),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            LanguageSelector(language, onLanguageSelected)

            Spacer(Modifier.height(20.dp))
            Text(
                text = stringResource(R.string.settings_more),
                fontSize = 12.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = stringResource(R.string.about_body),
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.weight(1f))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    text = stringResource(R.string.settings_version),
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    text = version,
                    fontSize = 12.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun LanguageSelector(current: String, onSelected: (String) -> Unit) {
    val options = listOf(
        "en" to R.string.lang_en,
        "zh" to R.string.lang_zh,
        "vi" to R.string.lang_vi,
    )
    var expanded by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { expanded = true }, modifier = Modifier.fillMaxWidth()) {
            Text(
                text = stringResource(
                    options.firstOrNull { it.first == current }?.second ?: R.string.lang_en
                )
            )
            Spacer(Modifier.weight(1f))
            Icon(imageVector = Icons.Filled.ArrowDropDown, contentDescription = null)
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            options.forEach { (code, labelRes) ->
                DropdownMenuItem(
                    text = { Text(stringResource(labelRes)) },
                    onClick = {
                        expanded = false
                        onSelected(code)
                    },
                )
            }
        }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun HostChip(
    profile: HostProfile,
    selected: Boolean,
    onClick: () -> Unit,
    onLongClick: () -> Unit
) {
    val chipShape = RoundedCornerShape(50)
    Surface(
        shape = chipShape,
        color = if (selected) {
            MaterialTheme.colorScheme.primary.copy(alpha = 0.18f)
        } else {
            MaterialTheme.colorScheme.surfaceVariant
        },
        border = BorderStroke(
            width = 1.dp,
            color = if (selected) {
                MaterialTheme.colorScheme.primary
            } else {
                MaterialTheme.colorScheme.outline
            }
        )
    ) {
        Text(
            text = profile.name,
            fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
            color = MaterialTheme.colorScheme.onSurface,
            // The press ripple has to be inside the pill: left on the Surface's
            // own modifier it is drawn outside the shape and paints as a hard
            // rectangle behind the rounded chip.
            modifier = Modifier
                .clip(chipShape)
                .combinedClickable(onClick = onClick, onLongClick = onLongClick)
                .padding(horizontal = 14.dp, vertical = 8.dp)
        )
    }
}

@Composable
private fun HostDialog(
    title: String,
    confirmLabel: String,
    initialName: String = "",
    initialAddress: String = "",
    initialDescription: String = "",
    onDismiss: () -> Unit,
    onConfirm: (String, String, String) -> Unit,
    onDelete: (() -> Unit)? = null
) {
    var name by remember { mutableStateOf(initialName) }
    var address by remember { mutableStateOf(initialAddress) }
    var description by remember { mutableStateOf(initialDescription) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    singleLine = true,
                    label = { Text(stringResource(R.string.host_name)) },
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = address,
                    onValueChange = { address = it },
                    singleLine = true,
                    label = { Text(stringResource(R.string.host_ip)) },
                    placeholder = { Text(stringResource(R.string.address_hint)) },
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    singleLine = true,
                    label = { Text(stringResource(R.string.host_description)) },
                    modifier = Modifier.fillMaxWidth()
                )
            }
        },
        confirmButton = {
            TextButton(
                enabled = name.isNotBlank() && address.isNotBlank(),
                onClick = { onConfirm(name.trim(), address.trim(), description.trim()) }
            ) {
                Text(confirmLabel)
            }
        },
        dismissButton = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (onDelete != null) {
                    TextButton(onClick = onDelete) {
                        Text(
                            text = stringResource(R.string.host_delete),
                            color = MaterialTheme.colorScheme.error
                        )
                    }
                }
                TextButton(onClick = onDismiss) {
                    Text(stringResource(R.string.cancel))
                }
            }
        }
    )
}

@Composable
private fun StatusCard(state: MicState) {
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = MaterialTheme.shapes.large,
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 20.dp, vertical = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = stringResource(R.string.host_status),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                fontSize = 12.sp
            )
            val (label, color) = statusAppearance(state)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(color = color, shape = CircleShape, modifier = Modifier.size(10.dp)) {}
                Spacer(Modifier.size(8.dp))
                Text(text = label, color = color, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun statusAppearance(state: MicState): Pair<String, Color> {
    return when (state.phase) {
        MicPhase.IDLE -> stringResource(R.string.status_idle) to MaterialTheme.colorScheme.onSurfaceVariant
        MicPhase.CONNECTING -> stringResource(R.string.status_connecting) to Color(0xFFFF9800)
        MicPhase.STREAMING -> if (state.muted) {
            stringResource(R.string.status_muted) to Color(0xFFFFB3AE)
        } else {
            stringResource(R.string.status_streaming) to Color(0xFF4CAF50)
        }
        MicPhase.ERROR -> stringResource(R.string.status_error) to MaterialTheme.colorScheme.error
    }
}

@Composable
private fun micAppearance(state: MicState): Triple<Color, ImageVector, Color> {
    return when {
        state.phase == MicPhase.IDLE -> Triple(
            MaterialTheme.colorScheme.surfaceVariant,
            Icons.Filled.Mic,
            MaterialTheme.colorScheme.onSurfaceVariant
        )
        state.muted -> Triple(
            Color(0xFFFFB3AE),
            Icons.Filled.MicOff,
            Color(0xFF4A0005)
        )
        else -> Triple(
            MaterialTheme.colorScheme.primary,
            Icons.Filled.Mic,
            MaterialTheme.colorScheme.onPrimary
        )
    }
}
