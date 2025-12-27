import { onMounted, onWillUnmount, useRef, useState } from '@odoo/owl';
import { ConfirmationDialog } from '@web/core/confirmation_dialog/confirmation_dialog';
import { CharField, charField } from '@web/views/fields/char/char_field';
import { registry } from '@web/core/registry';

/** @type {typeof import('qr-scanner').default} */
const QrScanner = window.QrScanner;

class QRCodeWidget extends CharField {
    static template = 'product_connect.QRCodeWidget';
    static props = {
        ...CharField.props,
    }

    setup() {
        super.setup();
        this.state = useState({
            scanEnabled: true,
            buttonLabel: 'Stop',
            flashlightLabel: undefined,
        })
        this.qrReaderRef = useRef('qrReader')

        this.onScanSuccess = this.onScanSuccess.bind(this);
        onMounted(async () => {
            this.qrScanner = new QrScanner(
                this.qrReaderRef.el,
                this.onScanSuccess,
                { returnDetailedScanResult: true }
            )

            this.startScanner()
            if (this.qrScanner.hasFlash().catch((error) => this.logError(error))) {
                this.state.flashlightLabel = "Flash on"
            }
        })

        onWillUnmount(() => {
            this.qrScanner.destroy()
        })
    }

    onScanSuccess(result) {
        const handleConfirm = () => {
            this.startScanner();
        };
        try {
            this.stopScanner();
            this.props.record.update({ [this.props.name]: result.data })
                .catch((error) => {
                    this.env.services.dialog.add(ConfirmationDialog, {
                        title: 'Error',
                        body: error,
                        confirm: handleConfirm,
                    });
                })
        } catch (error) {
            console.error('An error occurred:', error)
        }
    }

    startScanner() {
        this.qrScanner.start().catch((error) => this.logError(error));
        this.state.buttonLabel = 'Stop'
        this.state.scanEnabled = true;
        this.qrReaderRef.el.classList.remove('d-none');
    }

    stopScanner() {
        this.qrScanner.stop();
        this.state.buttonLabel = 'Scan'
        this.state.scanEnabled = false;
        this.qrReaderRef.el.classList.add('d-none');
    }

    toggleScan() {
        if (this.state.scanEnabled) {
            this.stopScanner()
        } else {
            this.startScanner()
        }
    }

    toggleFlashlight() {
        if (this.state.flashlightLabel === 'Flash On') {
            this.qrScanner.turnFlashOn().catch((error) => this.logError(error));
            this.state.flashlightLabel = 'Flash Off';
        } else {
            this.qrScanner.turnFlashOff().catch((error) => this.logError(error));
            this.state.flashlightLabel = 'Flash On';
        }
    }

    onInputFocus() {
        this.startScanner()
    }

    logError(error) {
        console.error('An error occurred:', error)
    }
}

export const qrCodeWidget = {
    ...charField,
    component: QRCodeWidget,
};

registry.category('fields').add('qr_scanner', qrCodeWidget);
