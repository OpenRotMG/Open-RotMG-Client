package {
    import flash.display.Sprite;
    import flash.events.Event;
    import flash.geom.Rectangle;
    import flash.text.TextField;
    import flash.text.TextFieldType;
    import flash.text.TextFormat;

    public class Test extends Sprite {
        private var field:TextField = new TextField();
        private var frame:int = 0;
        private var original:String = new Array(121).join("W");
        private var positions:Array = [120, 121, 0, 121, 120, 120, 119, 119, 1];
        private var lengths:Array = [120, 121, 121, 121, 121, 120, 119, 119, 1];

        public function Test() {
            field.defaultTextFormat = new TextFormat("_sans", 14);
            field.type = TextFieldType.INPUT;
            field.width = 80;
            field.height = 22;
            field.maxChars = 128;
            field.text = original;
            addChild(field);
            stage.focus = field;
            field.setSelection(field.length, field.length);
            addEventListener(Event.ENTER_FRAME, tick);
        }

        private function tick(event:Event):void {
            frame++;
            if (frame <= positions.length) {
                var end:Boolean = field.caretIndex == field.length;
                var bounds:Rectangle = field.getCharBoundaries(field.caretIndex - (end ? 1 : 0));
                var x:Number = (end ? bounds.right : bounds.left) - field.scrollH;
                var expected:String = frame == 9 ? "R" :
                    frame >= 7 ? original.substr(0, 119) :
                    frame >= 2 && frame <= 5 ? original + "X" : original;
                trace(frame, field.caretIndex == positions[frame - 1],
                    field.length == lengths[frame - 1], field.text == expected,
                    x >= 2 && x <= field.width - 2,
                    field.scrollH >= 0 && field.scrollH <= field.maxScrollH);
                return;
            }
            stage.focus = null;
            field.text = original;
            field.setSelection(field.length, field.length);
            trace("unfocused", field.scrollH == 0);
            field.type = TextFieldType.DYNAMIC;
            stage.focus = field;
            field.setSelection(field.length, field.length);
            trace("readonly", field.scrollH == 0);
            field.type = TextFieldType.INPUT;
            field.wordWrap = true;
            field.setSelection(field.length, field.length);
            trace("wrapped", field.scrollH == 0);
            field.wordWrap = false;
            field.multiline = true;
            field.setSelection(field.length, field.length);
            trace("multiline unchanged", field.scrollH == 0);
            removeEventListener(Event.ENTER_FRAME, tick);
        }
    }
}
