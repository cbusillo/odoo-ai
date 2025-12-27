declare module 'qr-scanner' {
    // noinspection JSUnusedGlobalSymbols
    export default class QrScanner {
        constructor(
            videoElem: HTMLVideoElement,
            onDecode: (result: QrScanner.ScanResult) => void,
            options?: QrScanner.Options
        );

        static hasCamera(): Promise<boolean>;

        start(): Promise<void>;

        stop(): void;

        destroy(): void;

        hasFlash(): Promise<boolean>;

        turnFlashOn(): Promise<void>;

        turnFlashOff(): Promise<void>;
    }

    namespace QrScanner {
        interface ScanResult {
            data: string;
            cornerPoints: [
                { x: number; y: number },
                { x: number; y: number },
                { x: number; y: number },
                { x: number; y: number }
            ];
        }

        interface Options {
            returnDetailedScanResult?: boolean;
            highlightScanRegion?: boolean;
            highlightCodeOutline?: boolean;
            overlay?: HTMLDivElement;
        }
    }
}