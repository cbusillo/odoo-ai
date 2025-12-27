export async function resizeImage(file, maxWidth, maxHeight) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = (event) => {
            const imageDataURL = event.target.result.toString()
            const image = new Image()
            image.onload = () => {
                const scale = Math.min(maxWidth / image.width, maxHeight / image.height, 1)
                const width = image.width * scale
                const height = image.height * scale

                /** @type {HTMLCanvasElement} */
                const canvas = document.createElement('canvas')
                canvas.width = width
                canvas.height = height

                const ctx = canvas.getContext('2d')
                ctx.drawImage(image, 0, 0, width, height)
                let outputType = file.type
                if (file.type === 'image/heic') {
                    outputType = 'image/jpeg'
                    file.name = file.name.replace(/\.heic$/, '.jpg')
                }

                resolve(canvas.toDataURL(outputType, 0.8).split(',')[1])
            }
            image.onerror = (error) => reject(error)
            image.src = imageDataURL
        }
        reader.onerror = (error) => reject(error)
        reader.readAsDataURL(file)
    })
}